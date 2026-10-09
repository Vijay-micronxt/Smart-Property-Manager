"""Online payment gateways behind one interface.

The portal and the CRM ask for "a way to collect this amount on this
instalment" without knowing which gateway a client uses -- Razorpay today,
something else tomorrow, or none at all (then the customer is shown the
payment instructions from Property Core Settings and staff record the money
with crm.billing.record_payment).

A gateway is a class registered under the ``property_payment_gateways`` hook,
so another app can add one without touching this one:

    property_payment_gateways = ["my_app.payments.PhonePeGateway"]

It offers one or both modes:

  checkout -- the frontend opens the gateway's own widget in the page and
              hands the result back to ``confirm``;
  link     -- a hosted payment URL to open, or to send by WhatsApp / SMS.
              After paying, the gateway sends the customer's browser to
              ``api.payments.link_return``, which records the payment and
              redirects to the frontend's ``return_url``; the gateway's
              webhook settles it too, for a customer who closes the tab.

Whatever the gateway, the money lands as a Payment Entry against the
instalment's Sales Invoice, and plan_status takes it from there.
"""

import frappe
from frappe import _


class PaymentGateway:
    #: shown to users and returned by the API
    name = ""
    #: "checkout", "link"
    modes = ()

    def is_enabled(self):
        raise NotImplementedError

    def start_checkout(self, ctx):
        """Return what the frontend needs to open the gateway widget."""
        raise NotImplementedError

    def confirm_checkout(self, payload):
        """Verify the widget's result and record the payment.
        Return ``{"paid": bool, "payment_entry": name or None, ...}``."""
        raise NotImplementedError

    def create_link(self, ctx):
        """Return ``{"url": ..., "id": ...}`` for a hosted payment page.
        Send the customer back to ``ctx.callback_url`` after paying, and keep
        ``ctx.return_url`` for ``handle_link_return``."""
        raise NotImplementedError

    def owns_link_return(self, params):
        """True when ``params`` (the query string the gateway appended to
        the callback URL) came from this gateway."""
        return False

    def handle_link_return(self, params):
        """Verify the return and record the payment. Return
        ``{"status": "success" | "pending" | "failed", "target", "invoice",
        "payment_entry", "amount", "return_url"}``."""
        raise NotImplementedError


def all_gateways():
    gateways = []
    for path in frappe.get_hooks("property_payment_gateways"):
        try:
            gateways.append(frappe.get_attr(path)())
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Payment gateway failed to load: {path}")
    return gateways


def enabled_gateways():
    out = []
    for gateway in all_gateways():
        try:
            if gateway.is_enabled():
                out.append(gateway)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Payment gateway check failed: {gateway.name}")
    return out


def get_gateway(name=None, mode=None):
    gateways = [g for g in enabled_gateways() if not mode or mode in g.modes]
    if name:
        gateways = [g for g in gateways if g.name.lower() == str(name).lower()]
    if not gateways:
        if name:
            frappe.throw(_("Payment gateway {0} is not enabled{1}").format(
                name, _(" for {0}").format(mode) if mode else ""))
        frappe.throw(_("No online payment gateway is enabled{0}").format(
            _(" for {0}").format(mode) if mode else ""))
    return gateways[0]
