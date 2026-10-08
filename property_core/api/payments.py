"""Collect a payment online -- one API for the customer portal and the CRM.

    GET  property_core.api.payments.options?target=BKG-0018
         -> enabled gateways and their modes, what is due now, and the payment
            instructions to show when no gateway is enabled

    POST property_core.api.payments.start
         target=BKG-0018 | PP-0054 | ACC-SINV-...   (booking = its next unpaid instalment)
         amount=<rupees, optional: defaults to the full amount due on that instalment>
         mode=checkout | link
         gateway=<optional: first enabled one that supports the mode>
         -> checkout: {"checkout": {"script", "options", "confirm_fields"}}
            link:     {"link": {"url", "id"}, "share_text"}

    POST property_core.api.payments.confirm
         gateway=Razorpay  payload={...the checkout widget's response...}
         -> {"paid", "payment_entry", ...}

    GET  property_core.api.payments.status?target=...
         -> what is still due -- poll this after sending a link

Who may call: a portal customer for their own bookings and invoices; staff
who can read the booking / invoice (a sales executive sending a link from the
CRM). Money a customer hands over in person -- cash, cheque, NEFT -- is not a
gateway payment: record it with ``crm.billing.record_payment``.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from property_core.api.utils import ok
from property_core.property_core import payments as gateways
from property_core.property_core.api.ecommerce import billing_context
from property_core.property_core.utils import settings


@frappe.whitelist()
def options(target=None):
    """Which gateways are enabled (and their modes), the payment instructions
    to show when none is, and -- with ``target`` -- what is due on it now."""
    enabled = gateways.enabled_gateways()
    data = {
        "gateways": [{"name": g.name, "modes": list(g.modes)} for g in enabled],
        "instructions": settings.get("payment_instructions"),
        "online": bool(enabled),
    }
    if target:
        ctx = _context(target)
        data["due"] = {
            "target": ctx.target,
            "invoice": ctx.invoice,
            "description": ctx.description,
            "amount": ctx.due,
        }
    return ok(data=data)


@frappe.whitelist(methods=["POST"])
def start(target, amount=None, mode="checkout", gateway=None):
    """Start an online payment on a booking (its next unpaid instalment), an
    instalment or an invoice. ``mode=link`` returns a hosted URL and share text;
    ``mode=checkout`` returns the options for the gateway's in-page widget.
    ``amount`` defaults to, and may not exceed, what is due."""
    if mode not in ("checkout", "link"):
        frappe.throw(_("mode must be checkout or link"))
    ctx = _context(target)

    amount = flt(amount) if amount not in (None, "") else ctx.due
    if amount <= 0:
        frappe.throw(_("Nothing is due on {0}").format(target))
    if amount > ctx.due + 0.005:
        frappe.throw(
            _("{0} is due on {1}; a payment cannot be more than that").format(
                frappe.format_value(ctx.due, {"fieldtype": "Currency"}), ctx.description
            )
        )
    ctx.amount = flt(amount, 2)

    gw = gateways.get_gateway(gateway, mode)
    if mode == "checkout":
        return ok(data={"gateway": gw.name, "mode": mode, "amount": ctx.amount, "invoice": ctx.invoice,
                        "checkout": gw.start_checkout(ctx)})

    link = gw.create_link(ctx)
    share_text = _("Dear {0}, please pay {1} for {2}: {3}").format(
        ctx.customer_name or ctx.customer,
        frappe.format_value(ctx.amount, {"fieldtype": "Currency"}),
        ctx.description,
        link["url"],
    )
    return ok(data={"gateway": gw.name, "mode": mode, "amount": ctx.amount, "invoice": ctx.invoice,
                    "link": link, "share_text": share_text})


@frappe.whitelist(methods=["POST"])
def confirm(gateway, payload):
    """Hand back the checkout widget's response, as-is. Verifies it with the
    gateway and records the Payment Entry."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    gw = gateways.get_gateway(gateway, "checkout")
    return ok(data=gw.confirm_checkout(frappe._dict(payload)))


@frappe.whitelist()
def status(target):
    """What is still due on ``target`` -- poll this after sending a link."""
    ctx = _context(target, raise_invoice=False)
    return ok(data={"target": ctx.target, "invoice": ctx.invoice, "description": ctx.description,
                    "due": ctx.due, "paid": ctx.due <= 0.005})


# ------------------------------------------------------------------ #

def _context(target, raise_invoice=True):
    """Who pays what, for ``target``, after checking the caller may see it."""
    doctype = billing_context.get_doctype(target)
    doc = frappe.get_doc(doctype, target)
    customer, email, phone = billing_context.get_contact(doctype, doc)
    _check_access(doctype, doc, customer)

    invoice = None
    description = target
    if doctype in billing_context.PROPERTY_DOCTYPES:
        if raise_invoice:
            invoice = billing_context.resolve_sales_invoice(target, doctype)
        else:
            row = (
                billing_context.next_unpaid_instalment(target) if doctype == "Property Booking"
                else frappe.db.get_value("Payment Plan", target, ["name", "invoice"], as_dict=True)
            )
            invoice = row and row.get("invoice")
        plan = frappe.db.get_value(
            "Payment Plan", {"invoice": invoice} if invoice else (
                {"name": target} if doctype == "Payment Plan" else {"booking": target}
            ),
            ["milestone", "booking", "outstanding_amount"], as_dict=True,
        )
        if plan:
            description = _("{0} on {1}").format(plan.milestone, plan.booking)
    elif doctype == "Sales Invoice":
        invoice = target

    due = flt(frappe.db.get_value("Sales Invoice", invoice, "outstanding_amount")) if invoice else 0
    return frappe._dict(
        target=target,
        doctype=doctype,
        invoice=invoice,
        customer=customer,
        customer_name=frappe.db.get_value("Customer", customer, "customer_name") if customer else None,
        email=email,
        phone=phone,
        description=description,
        due=flt(due, 2),
    )


def _check_access(doctype, doc, customer):
    if frappe.session.user == "Guest":
        frappe.throw(_("Please login"), frappe.AuthenticationError)
    if frappe.get_cached_value("User", frappe.session.user, "user_type") == "Website User":
        from property_core.api.portal.base import get_customer

        if not customer or customer != get_customer():
            frappe.throw(_("Not permitted"), frappe.PermissionError)
        return
    if not frappe.has_permission(doctype, "read", doc):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
