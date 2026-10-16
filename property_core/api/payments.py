"""Collect a payment online -- one API for the customer portal and the CRM.

    The gateway is the site's choice, not the frontend's: Online Payment
    Gateway in Property Core Settings (Razorpay or mSwipe; blank = the first
    one set up). The frontend calls the same endpoints whichever it is.

    GET  property_core.api.payments.options?target=BKG-0018
         -> the gateway in use and its modes, what is due now, and the payment
            instructions to show when no gateway is set up

    POST property_core.api.payments.start
         target=BKG-0018 | PP-0054 | ACC-SINV-...   (booking = its next unpaid instalment)
         amount=<rupees, optional: defaults to the full amount due on that instalment>
         mode=<optional: link (default) | checkout; a gateway without checkout
               (mSwipe) answers with a link>
         return_url=<link mode, optional: where the customer's browser lands
                     after paying -- the frontend page; see link_return>
         phone=<optional: the customer's mobile, when none is on file or
                another should get the link; gateways with needs_phone
                (mSwipe) cannot start without one>
         -> checkout: {"checkout": {"script", "options", "confirm_fields"}}
            link:     {"link": {"url", "id"}, "share_text"}

    POST property_core.api.payments.confirm
         payload={...the checkout widget's response...}
         -> {"paid", "payment_entry", ...}

    GET  property_core.api.payments.status?target=...
         -> what is still due -- poll this after sending a link

    GET  property_core.api.payments.link_return   (the gateway calls it, not you)
         After paying on a link, the gateway sends the customer here. It
         verifies the payment, records the Payment Entry, then redirects to
         the link's return_url with
             ?payment=success|pending|failed&target=&invoice=&payment_entry=&amount=
         Read those on that page to show the result; call status to be sure.
         Without a return_url the customer sees a plain result page instead.
         return_url must be on this site, or on a host listed under Allowed
         Return Hosts in Property Core Settings.

Who may call: a portal customer for their own bookings and invoices; staff
who can read the booking / invoice (a sales executive sending a link from the
CRM). Money a customer hands over in person -- cash, cheque, NEFT -- is not a
gateway payment: record it with ``crm.billing.record_payment``.
"""

import json
from urllib.parse import urlencode, urlparse

import frappe
from frappe import _
from frappe.utils import escape_html, flt, get_url

from property_core.api.utils import ok
from property_core.property_core import payments as gateways
from property_core.property_core.api.ecommerce import billing_context
from property_core.property_core.utils import settings


@frappe.whitelist()
def options(target=None):
    """The gateway customers pay through (set in Property Core Settings),
    the payment instructions to show when there is none, and -- with
    ``target`` -- what is due on it now."""
    gw = gateways.selected_gateway()
    info = gw and {"name": gw.name, "modes": list(gw.modes), "needs_phone": gw.needs_phone}
    data = {
        "online": bool(gw),
        "gateway": info,
        "gateways": [info] if info else [],  # older frontends read this list
        "instructions": settings.get("payment_instructions"),
    }
    if target:
        ctx = _context(target)
        data["due"] = {
            "target": ctx.target,
            "invoice": ctx.invoice,
            "description": ctx.description,
            "amount": ctx.due,
            # False: a gateway with needs_phone must be sent `phone` in start
            "has_phone": bool(ctx.phone),
        }
    return ok(data=data)


@frappe.whitelist(methods=["POST"])
def start(target, amount=None, mode=None, gateway=None, return_url=None, phone=None):
    """Start an online payment on a booking (its next unpaid instalment), an
    instalment or an invoice, through the gateway set in Property Core
    Settings. ``mode=link`` (default) returns a hosted URL and share text;
    ``mode=checkout`` returns the options for the gateway's in-page widget, or
    a link when the gateway has no widget -- read ``mode`` in the response.
    ``gateway`` is ignored (kept so older frontends that send it still work).
    ``amount`` defaults to, and may not exceed, what is due. ``return_url``:
    where a link sends the customer after paying (see ``link_return``).
    ``phone``: the customer's mobile, overriding the one on file."""
    if mode not in (None, "", "checkout", "link"):
        frappe.throw(_("mode must be checkout or link"))
    gw = gateways.selected_gateway()
    if not gw:
        frappe.throw(_("Online payment is not set up. Pick the gateway under Online Payment Gateway "
                       "in Property Core Settings and fill in its Settings."))
    mode = mode if mode in gw.modes else "link"
    ctx = _context(target)
    ctx.return_url = _check_return_url(return_url)
    ctx.callback_url = get_url("/api/method/property_core.api.payments.link_return")
    if phone not in (None, ""):
        if len("".join(c for c in str(phone) if c.isdigit())) < 10:
            frappe.throw(_("phone must be a 10-digit mobile number"))
        ctx.phone = str(phone).strip()

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
def confirm(payload, gateway=None):
    """Hand back the checkout widget's response, as-is. Verifies it with the
    gateway and records the Payment Entry."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    gw = gateways.selected_gateway()
    if not gw or "checkout" not in gw.modes:
        gw = gateways.get_gateway(gateway, "checkout")
    return ok(data=gw.confirm_checkout(frappe._dict(payload)))


@frappe.whitelist()
def status(target):
    """What is still due on ``target`` -- poll this after sending a link."""
    ctx = _context(target, raise_invoice=False)
    return ok(data={"target": ctx.target, "invoice": ctx.invoice, "description": ctx.description,
                    "due": ctx.due, "paid": ctx.due <= 0.005})


@frappe.whitelist(allow_guest=True, methods=["GET"])
def link_return(**params):
    """Where a payment link sends the customer's browser after paying. Guest:
    the customer is usually not logged in, and the gateway's signature is
    what proves the payment. Records it, then redirects to the link's
    return_url with ``payment=success|pending|failed`` and the details."""
    params.pop("cmd", None)
    params = frappe._dict(params)
    result = {"status": "failed"}
    try:
        gw = next(
            (g for g in gateways.enabled_gateways() if "link" in g.modes and g.owns_link_return(params)),
            None,
        )
        if not gw:
            frappe.throw(_("This payment return is not from an enabled gateway"))
        result = gw.handle_link_return(params)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="Payment link return failed",
            message=frappe.get_traceback() + "\n\n" + json.dumps(params, default=str),
        )

    status = result.get("status") or "failed"
    if result.get("return_url"):
        query = {k: result.get(k) for k in ("target", "invoice", "payment_entry", "amount") if result.get(k)}
        url = result["return_url"]
        url += ("&" if "?" in url else "?") + urlencode({"payment": status, **query})
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = url
        return

    amount = frappe.format_value(result.get("amount"), {"fieldtype": "Currency"}) if result.get("amount") else ""
    for_what = escape_html(result.get("target") or "")
    page = {
        "success": (_("Payment received"), _("Thank you. {0} received for {1}. Receipt: {2}").format(
            amount, for_what, escape_html(result.get("payment_entry") or "")), "green"),
        "pending": (_("Payment processing"), _("Your payment for {0} is being confirmed by the bank. "
                    "It will show on your account shortly.").format(for_what), "orange"),
        "failed": (_("Payment not completed"), _("We could not confirm this payment. If money was "
                   "deducted, it will be reconciled automatically; otherwise please try the link again."), "red"),
    }[status]
    frappe.respond_as_web_page(page[0], page[1], indicator_color=page[2])


# ------------------------------------------------------------------ #

def _check_return_url(url):
    """``url`` as an absolute URL if the customer may be sent there: this
    site, or a host under Allowed Return Hosts (the frontend's domain). Any
    other host would turn our payment links into a redirect to anywhere."""
    if not url:
        return None
    if url.startswith("/") and not url.startswith("//"):
        return get_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        frappe.throw(_("return_url must be an http(s) URL"))
    allowed = {urlparse(get_url()).netloc.lower()}
    for line in (settings.get("payment_return_hosts") or "").splitlines():
        line = line.strip()
        if line:
            allowed.add((urlparse(line).netloc if "://" in line else line).lower().rstrip("/"))
    if parsed.netloc.lower() not in allowed:
        frappe.throw(
            _("return_url host {0} is not allowed. Add it under Allowed Return Hosts in Property Core Settings.").format(
                parsed.netloc
            )
        )
    return url


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
