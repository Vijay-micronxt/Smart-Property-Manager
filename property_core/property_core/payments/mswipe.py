"""mSwipe: a hosted payment page; its callback settles the invoice."""

import frappe
from frappe import _
from frappe.utils import flt

from property_core.property_core.payments import PaymentGateway


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
        return bool(s and (s.cust_code or s.user_id) and s.password)

    def create_link(self, ctx):
        from property_core.property_core.api.ecommerce import mswipe_integration

        if not ctx.phone:
            frappe.throw(_("mSwipe needs the customer's mobile number"))
        result = mswipe_integration.order_payment(
            ctx.target, flt(ctx.amount), mobileno=ctx.phone, email=ctx.email,
        )
        if result.get("status") != 200:
            frappe.throw(result.get("error") or _("mSwipe could not start the payment"))
        order = result["data"]["order"]
        return {"url": order["payment_url"], "id": order.get("trans_id") or order.get("txn_id")}
