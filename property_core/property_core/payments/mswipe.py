"""mSwipe Pay-by-Link: a hosted payment page.

mSwipe has no webhook for Pay-by-Link. After paying, it sends the customer's
browser to the ``redirect_url`` given when the link was made -- here
``api.payments.link_return`` -- with ``encIpgId`` (or ``TransID``) in the query
string. That id is all we trust from the browser: the payment itself is read
back from mSwipe (``getPBLTransactionDetails``) before anything is posted.

A customer who pays and closes the tab never comes back, so
``reconcile_pending`` asks mSwipe about open links every few minutes and
settles the ones that were paid.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, now_datetime

from property_core.property_core.payments import PaymentGateway

PAID, PENDING = 1, 2  # getPBLTransactionDetails Payment_Status; anything else = not paid (yet)


class MswipeAdapter(PaymentGateway):
    name = "mSwipe"
    modes = ("link",)

    def is_enabled(self):
        if not frappe.db.exists("DocType", "Mswipe Settings"):
            return False
        try:
            from property_core.property_core.api.ecommerce.mswipe_integration import _load_mswipe_settings

            s = _load_mswipe_settings()
        except Exception:
            return False
        return bool(s and s.base_url and s.cust_code and s.user_id and s.client_id and s.password)

    def create_link(self, ctx):
        from property_core.property_core.api.ecommerce.mswipe_integration import (
            MSWIPE_ATTEMPT_BY_TRANSID_PREFIX,
            MswipeGateway,
        )

        if not ctx.phone:
            frappe.throw(_("mSwipe needs the customer's mobile number"))
        if not ctx.invoice:
            frappe.throw(_("Nothing to collect on {0}").format(ctx.target))

        # each link gets its own invoice_id: a second link for the same
        # instalment (the first expired, or was lost) must not overwrite the
        # first one's record while it can still be paid
        reference = f"{ctx.target}-{frappe.generate_hash(length=6)}"
        gateway = MswipeGateway()
        result = gateway.initiate_transaction(
            order_id=reference,
            amount=flt(ctx.amount),
            mobileno=_mobile(ctx.phone),
            email=ctx.email,
            callback_url=ctx.callback_url,
            return_url=ctx.return_url,
        )

        name = frappe.db.get_value("Mswipe Payment Entry", {"mswipe_order_id": reference}, "name")
        frappe.db.set_value("Mswipe Payment Entry", name, {
            "sales_invoice": ctx.invoice,
            "customer": ctx.customer,
            "notes": json.dumps({"target": ctx.target}),
        })
        if result.get("trans_id"):
            frappe.cache().set_value(
                MSWIPE_ATTEMPT_BY_TRANSID_PREFIX + result["trans_id"], {"order_id": reference},
                expires_in_sec=3600,
            )
        return {"url": result["payment_url"], "id": result.get("trans_id") or reference}

    def owns_link_return(self, params):
        return bool(params.get("encIpgId") or params.get("TransID"))

    def handle_link_return(self, params):
        trans_id = params.get("encIpgId") or params.get("TransID")
        entry = _entry_for(trans_id)
        if not entry:
            frappe.throw(_("Unknown mSwipe payment {0}").format(trans_id))

        result = {
            "status": "failed",
            "target": json.loads(entry.notes or "{}").get("target"),
            "invoice": entry.sales_invoice,
            "amount": flt(entry.amount),
            "return_url": entry.return_url,
        }
        if entry.payment_entry:
            result.update(status="success", payment_entry=entry.payment_entry)
            return result

        row = _fetch(entry.mswipe_trans_id or trans_id)
        status = cint(row.get("Payment_Status")) if row else None
        if status == PENDING:
            frappe.db.set_value("Mswipe Payment Entry", entry.name, "status", "PENDING")
            result["status"] = "pending"
            return result
        if status != PAID:
            # an open link reads "not paid" until it is paid -- leave it open,
            # the customer may still try again
            return result

        result["amount"] = _paid_amount(row) or result["amount"]
        try:
            result["payment_entry"] = settle(entry.name, row)
        except Exception:
            # the money is taken; only our booking of it failed. Keep the
            # customer on the frontend and let reconcile_pending post it.
            frappe.db.rollback()
            frappe.log_error(title="mSwipe settle failed", message=frappe.get_traceback())
            result["status"] = "pending"
            return result
        result["status"] = "success"
        return result


def settle(entry_name, row):
    """Record the paid mSwipe transaction ``row`` against the invoice its link
    was raised for. The customer's return and reconcile_pending can both get
    here: the row lock lets one of them post the Payment Entry. Returns its
    name."""
    from property_core.property_core.api.ecommerce.mswipe_integration import (
        MswipeGateway,
        create_payment_entry_from_mswipe,
    )

    frappe.db.get_value("Mswipe Payment Entry", entry_name, "name", for_update=True)
    entry = frappe.get_doc("Mswipe Payment Entry", entry_name)
    if entry.payment_entry:
        return entry.payment_entry

    gateway = MswipeGateway()
    txn_id = row.get("IPG_ID") or entry.mswipe_txn_id
    existing = txn_id and frappe.db.get_value(
        "Payment Entry", {"reference_no": txn_id, "docstatus": 1}, "name"
    )
    if existing:
        entry.db_set({"payment_entry": existing, "status": "COMPLETED"})
        return existing

    entry.mswipe_txn_id = txn_id
    entry.amount = _paid_amount(row) or entry.amount
    entry.status = "SUCCESS"
    entry.verified = 1
    entry.mswipe_response = json.dumps(row, default=str)
    entry.save(ignore_permissions=True)

    # the customer arrives as Guest (and the scheduler as Administrator):
    # post the Payment Entry as the configured user, as Razorpay does
    user = frappe.session.user
    frappe.set_user(_system_user(gateway.system_user))
    try:
        create_payment_entry_from_mswipe(
            entry, system_user=frappe.session.user, mode_of_payment=gateway.mode_of_payment
        )
    finally:
        frappe.set_user(user)
    return entry.payment_entry


def reconcile_pending():
    """Scheduler: settle mSwipe links that were paid but whose customer never
    came back to link_return (closed the tab, lost signal)."""
    if not any(isinstance(g, MswipeAdapter) for g in _enabled()):
        return
    open_entries = frappe.get_all(
        "Mswipe Payment Entry",
        filters={
            "status": ["in", ["INITIATED", "PENDING"]],
            "sales_invoice": ["is", "set"],
            "payment_entry": ["is", "not set"],
            "mswipe_trans_id": ["is", "set"],
            "creation": [">", add_days(now_datetime(), -3)],
        },
        fields=["name", "mswipe_trans_id"],
        limit=100,
    )
    for e in open_entries:
        try:
            row = _fetch(e.mswipe_trans_id)
            if row and cint(row.get("Payment_Status")) == PAID:
                settle(e.name, row)
                frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title=f"mSwipe reconcile failed: {e.name}", message=frappe.get_traceback())


# ------------------------------------------------------------------ #

def _enabled():
    from property_core.property_core import payments

    return payments.enabled_gateways()


def _entry_for(trans_id):
    from property_core.property_core.api.ecommerce.mswipe_integration import MSWIPE_ATTEMPT_BY_TRANSID_PREFIX

    fields = ["name", "sales_invoice", "amount", "notes", "return_url", "payment_entry", "mswipe_trans_id"]
    entry = frappe.db.get_value("Mswipe Payment Entry", {"mswipe_trans_id": trans_id}, fields, as_dict=True)
    if not entry:
        cached = frappe.cache().get_value(MSWIPE_ATTEMPT_BY_TRANSID_PREFIX + trans_id) or {}
        if cached.get("order_id"):
            entry = frappe.db.get_value(
                "Mswipe Payment Entry", {"mswipe_order_id": cached["order_id"]}, fields, as_dict=True
            )
    return entry


def _fetch(trans_id):
    from property_core.property_core.api.ecommerce.mswipe_integration import MswipeGateway

    return MswipeGateway().check_transaction_status(trans_id)


def _paid_amount(row):
    return flt(row.get("TxnAmount") or row.get("Amount"))


def _mobile(phone):
    """mSwipe wants the 10-digit number, without +91 or spaces."""
    digits = "".join(c for c in str(phone) if c.isdigit())
    return digits[-10:] if len(digits) > 10 else digits


def _system_user(user):
    if user and frappe.db.get_value("User", user, "enabled"):
        return user
    return "Administrator"
