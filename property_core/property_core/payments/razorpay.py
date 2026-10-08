"""Razorpay: Standard Checkout in the page, or a Payment Link to send."""

import json

import frappe
from frappe import _
from frappe.utils import flt

from property_core.property_core.payments import PaymentGateway

CHECKOUT_SCRIPT = "https://checkout.razorpay.com/v1/checkout.js"


class RazorpayAdapter(PaymentGateway):
    name = "Razorpay"
    modes = ("checkout", "link")

    def is_enabled(self):
        if not frappe.db.exists("DocType", "Razorpay Settings"):
            return False
        s = frappe.get_single("Razorpay Settings")
        return bool(s.api_key and s.api_secret)

    def start_checkout(self, ctx):
        from property_core.property_core.api.ecommerce import razorpay_integration

        result = razorpay_integration.order_payment(ctx.target, int(round(flt(ctx.amount) * 100)))
        if result.get("status") != 200:
            frappe.throw(result.get("error") or _("Razorpay could not create the order"))
        order = result["data"]["order"]
        return {
            "script": CHECKOUT_SCRIPT,
            # pass straight to `new Razorpay(options)` and add a `handler`
            "options": {
                "key": result["key"],
                "order_id": order["id"],
                "amount": int(round(flt(order["amount"]) * 100)),
                "currency": order.get("currency") or "INR",
                "name": frappe.defaults.get_global_default("company") or "",
                "description": ctx.description,
                "prefill": {"name": ctx.customer_name or "", "email": ctx.email or "", "contact": ctx.phone or ""},
                "notes": {"target": ctx.target},
            },
            # the handler's response, as-is, goes to payments.confirm as `payload`
            "confirm_fields": ["razorpay_payment_id", "razorpay_order_id", "razorpay_signature"],
        }

    def confirm_checkout(self, payload):
        from property_core.property_core.api.ecommerce import razorpay_integration

        missing = [k for k in ("razorpay_payment_id", "razorpay_order_id", "razorpay_signature") if not payload.get(k)]
        if missing:
            frappe.throw(_("Missing {0}").format(", ".join(missing)))
        result = razorpay_integration.verify_payment_signature(
            payload["razorpay_payment_id"], payload["razorpay_order_id"], payload["razorpay_signature"]
        )
        return {
            "paid": result.get("payment_status") in ("CAPTURED", "AUTHORIZED"),
            "reconciled": result.get("reconciled"),
            "payment_entry": result.get("payment_entry"),
            "sales_invoice": result.get("sales_invoice"),
            "gateway_reference": payload["razorpay_payment_id"],
        }

    def create_link(self, ctx):
        from property_core.property_core.api.ecommerce.razorpay_integration import RazorpayGateway

        gateway = RazorpayGateway()
        # Razorpay rejects a reference_id it has seen before; a second link for
        # the same instalment (the first expired, or was lost) needs its own
        reference = f"{ctx.target}-{frappe.generate_hash(length=6)}"
        link = gateway.create_payment_link(
            amount=int(round(flt(ctx.amount) * 100)),
            currency="INR",
            customer_email=ctx.email,
            customer_phone=ctx.phone,
            description=ctx.description,
            order_id=reference,
            accept_partial=False,
            notes={"target": ctx.target, "sales_invoice": ctx.invoice},
            customer_name=ctx.customer_name,
        )

        rpe = frappe.new_doc("Razorpay Payment Entry")
        rpe.name = frappe.generate_hash(length=10)
        rpe.customer = ctx.customer
        rpe.sales_invoice = ctx.invoice
        rpe.razorpay_link_id = link["id"]
        rpe.amount = flt(ctx.amount)
        rpe.currency = "INR"
        rpe.status = "INITIATED"
        rpe.payment_method = "razorpay"
        rpe.notes = json.dumps({"target": ctx.target, "short_url": link.get("short_url")})
        rpe.insert(ignore_permissions=True)

        return {"url": link.get("short_url"), "id": link["id"], "expires_at": link.get("expire_by")}


def handle_payment_link_paid(payload):
    """Webhook ``payment_link.paid``: settle the invoice the link was raised for."""
    from property_core.property_core.api.ecommerce.razorpay_integration import create_payment_entry_from_razorpay

    link = (payload.get("payment_link") or {}).get("entity") or {}
    payment = (payload.get("payment") or {}).get("entity") or {}
    name = frappe.db.get_value("Razorpay Payment Entry", {"razorpay_link_id": link.get("id")}, "name")
    if not name:
        return

    rpe = frappe.get_doc("Razorpay Payment Entry", name)
    if rpe.payment_entry:
        return  # already settled -- Razorpay retries webhooks

    rpe.razorpay_payment_id = payment.get("id")
    rpe.razorpay_order_id = payment.get("order_id") or rpe.razorpay_order_id
    rpe.amount = flt(payment.get("amount")) / 100 or rpe.amount
    rpe.status = "CAPTURED"
    rpe.razorpay_response = json.dumps(payment)
    rpe.save(ignore_permissions=True)

    if rpe.sales_invoice:
        create_payment_entry_from_razorpay(rpe)
