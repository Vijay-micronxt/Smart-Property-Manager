"""mSwipe Pay-by-Link: a hosted payment page.

mSwipe has no webhook for Pay-by-Link. After paying, it sends the customer's
browser to the ``redirect_url`` given when the link was made -- here
``api.payments.link_return`` -- with ``encIpgId`` (or ``TransID``) in the query
string. That id is all we trust from the browser: the payment itself is read
back from mSwipe (``getPBLTransactionDetails``) before anything is posted.

A customer who pays and closes the tab never comes back, so
``reconcile_pending`` asks mSwipe about open links every few minutes and
settles the ones that were paid, and ``payments.status`` asks about the
caller's own links on every poll (throttled), so a staff screen sees the
payment within seconds.

Every link is its own Mswipe Payment Entry (an "attempt"): part payments and
a re-sent link each get one, and settling is keyed on it, so one payment is
never recorded twice. A new link for an invoice supersedes the unpaid ones
before it; a superseded or expired link that is paid anyway is still recorded
(the money is taken) -- whatever the invoice cannot take stays as an advance.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

from property_core.property_core.payments import PaymentGateway

PAID, PENDING = 1, 2  # getPBLTransactionDetails Payment_Status; anything else = not paid (yet)
OPEN = ("INITIATED", "PENDING", "EXPIRED", "SUPERSEDED")  # no Payment Entry yet; mSwipe may still take money
DEFAULT_VALIDITY_HOURS = 24
RECHECK_SECONDS = 15  # payments.status asks mSwipe about one link at most this often


class MswipeAdapter(PaymentGateway):
    name = "mSwipe"
    modes = ("link",)
    needs_phone = True

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

        expires_at = add_to_date(now_datetime(), hours=_validity_hours())
        name = frappe.db.get_value("Mswipe Payment Entry", {"mswipe_order_id": reference}, "name")
        frappe.db.set_value("Mswipe Payment Entry", name, {
            "sales_invoice": ctx.invoice,
            "customer": ctx.customer,
            "target": ctx.target,
            "expires_at": expires_at,
            "notes": json.dumps({"target": ctx.target}),
        })
        # the older unpaid links on this invoice are now stale: the customer
        # should pay this one. They are still watched, in case they are paid.
        frappe.db.sql(
            """update `tabMswipe Payment Entry` set status = 'SUPERSEDED'
            where sales_invoice = %s and name != %s and status = 'INITIATED'
            and ifnull(payment_entry, '') = ''""",
            (ctx.invoice, name),
        )
        frappe.db.commit()
        if result.get("trans_id"):
            frappe.cache().set_value(
                MSWIPE_ATTEMPT_BY_TRANSID_PREFIX + result["trans_id"], {"order_id": reference},
                expires_in_sec=3600,
            )
        return {"url": result["payment_url"], "id": result.get("trans_id") or reference,
                "expires_at": str(expires_at)}

    def link_attempts(self, ctx, link_id=None, live=True):
        """The links raised on ``ctx.invoice``, newest first, as the API shows
        them. ``live``: ask mSwipe about the open ones (and settle those that
        were paid) before answering."""
        if link_id:
            names = frappe.get_all("Mswipe Payment Entry", filters={"mswipe_trans_id": link_id},
                                   pluck="name", limit=1) or frappe.get_all(
                "Mswipe Payment Entry", filters={"mswipe_order_id": link_id}, pluck="name", limit=1)
            if names:
                e = frappe.db.get_value("Mswipe Payment Entry", names[0], ["target", "sales_invoice"], as_dict=True)
                if ctx.target not in (e.target, e.sales_invoice) and e.sales_invoice != ctx.invoice:
                    frappe.throw(_("Payment link {0} is not for {1}").format(link_id, ctx.target))
        else:
            # a booking's "next instalment" moves on once one is paid: find
            # its links by the target they were raised for, too
            or_filters = {"target": ctx.target}
            if ctx.invoice:
                or_filters["sales_invoice"] = ctx.invoice
            names = frappe.get_all("Mswipe Payment Entry", or_filters=or_filters, pluck="name",
                                   order_by="creation desc", limit=10)

        if live:
            for name in names[:5]:
                _recheck(name)
        return [_attempt(name) for name in names]

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
            frappe.db.commit()  # link_return is a GET: Frappe rolls those back
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
    entry.paid_on = now_datetime()
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
    # link_return and payments.status are GET requests, which Frappe rolls
    # back at the end: the Payment Entry must be committed here
    frappe.db.commit()
    return entry.payment_entry


def reconcile_pending():
    """Scheduler: settle mSwipe links that were paid but whose customer never
    came back to link_return (closed the tab, lost signal)."""
    if not any(isinstance(g, MswipeAdapter) for g in _enabled()):
        return
    # expired by our clock: show it so, but keep asking -- mSwipe's own expiry
    # may be later, and a late payment must still be recorded
    frappe.db.sql(
        """update `tabMswipe Payment Entry` set status = 'EXPIRED'
        where status = 'INITIATED' and expires_at < %s and ifnull(payment_entry, '') = ''""",
        now_datetime(),
    )
    frappe.db.commit()
    open_entries = frappe.get_all(
        "Mswipe Payment Entry",
        filters={
            "status": ["in", OPEN],
            "sales_invoice": ["is", "set"],
            "payment_entry": ["is", "not set"],
            "mswipe_trans_id": ["is", "set"],
            "creation": [">", add_to_date(now_datetime(), hours=-_watch_hours())],
        },
        fields=["name", "mswipe_trans_id"],
        order_by="creation desc",
        limit=200,
    )
    for e in open_entries:
        try:
            _check(e.name, e.mswipe_trans_id)
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


def _check(name, trans_id):
    """Ask mSwipe about one open link; settle it if paid. Returns mSwipe's row."""
    row = _fetch(trans_id)
    status = cint(row.get("Payment_Status")) if row else None
    if status == PAID:
        settle(name, row)
    elif status == PENDING and frappe.db.get_value("Mswipe Payment Entry", name, "status") == "INITIATED":
        frappe.db.set_value("Mswipe Payment Entry", name, "status", "PENDING")
        frappe.db.commit()
    return row


def _recheck(name):
    """``_check`` for payments.status: only open links still being watched,
    and each at most once per RECHECK_SECONDS however often the app polls."""
    e = frappe.db.get_value("Mswipe Payment Entry", name,
                            ["status", "payment_entry", "mswipe_trans_id", "creation"], as_dict=True)
    if not e or e.payment_entry or e.status not in OPEN or not e.mswipe_trans_id:
        return
    if get_datetime(e.creation) < add_to_date(now_datetime(), hours=-_watch_hours()):
        return
    key = f"mswipe_recheck:{name}"
    if frappe.cache().get_value(key):
        return
    frappe.cache().set_value(key, 1, expires_in_sec=RECHECK_SECONDS)
    try:
        _check(name, e.mswipe_trans_id)
    except Exception:
        # mSwipe down or slow: answer from what we know; the job retries
        frappe.db.rollback()
        frappe.log_error(title=f"mSwipe status check failed: {name}", message=frappe.get_traceback())


def _attempt(name):
    e = frappe.db.get_value(
        "Mswipe Payment Entry", name,
        ["name", "mswipe_trans_id", "mswipe_order_id", "target", "sales_invoice", "amount", "status",
         "expires_at", "payment_entry", "paid_on", "creation", "mswipe_response"],
        as_dict=True,
    )
    if e.payment_entry:
        state = "paid"
    elif e.status == "FAILED":
        state = "failed"
    elif e.status == "PENDING":
        state = "pending"
    elif e.status == "SUPERSEDED":
        state = "superseded"
    elif e.status == "EXPIRED" or (e.expires_at and get_datetime(e.expires_at) < now_datetime()):
        state = "expired"
    else:
        state = "initiated"
    url = None
    try:
        resp = json.loads(e.mswipe_response or "{}")
        url = resp.get("smslink") or resp.get("shortUrl") or resp.get("link")
    except (ValueError, AttributeError):
        pass
    return {
        "link_id": e.mswipe_trans_id or e.mswipe_order_id,
        "reference": e.mswipe_order_id,
        "url": url if state in ("initiated", "pending") else None,
        "target": e.target,
        "invoice": e.sales_invoice,
        "amount": flt(e.amount),
        "status": state,
        "paid_amount": flt(e.amount) if state == "paid" else 0,
        "paid_on": str(e.paid_on) if e.paid_on else None,
        "payment_entry": e.payment_entry,
        "created_on": str(e.creation),
        "expires_at": str(e.expires_at) if e.expires_at else None,
    }


def _validity_hours():
    from property_core.property_core.api.ecommerce.mswipe_integration import _load_mswipe_settings

    try:
        return cint(_load_mswipe_settings().get("link_validity_hours")) or DEFAULT_VALIDITY_HOURS
    except Exception:
        return DEFAULT_VALIDITY_HOURS


def _watch_hours():
    """How long after it is made a link is still asked about: its validity
    and a day more, for a payment that is captured late."""
    return _validity_hours() + 24


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
