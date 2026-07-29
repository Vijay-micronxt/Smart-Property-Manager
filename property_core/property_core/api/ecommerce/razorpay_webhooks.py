import hashlib
import hmac
import json

import frappe
from frappe import _

from property_core.property_core.api.ecommerce.razorpay_integration import (
    RazorpayGateway,
    create_payment_entry_from_razorpay,
)


@frappe.whitelist(allow_guest=True)
def handle_razorpay_webhook():
    try:
        raw_body = frappe.request.get_data(as_text=True)
        signature = frappe.request.headers.get("X-Razorpay-Signature", "")

        settings = frappe.get_single("Razorpay Settings")
        webhook_secret = settings.get_password("webhook_secret") if settings.webhook_secret else None

        if webhook_secret:
            expected = hmac.new(
                webhook_secret.encode(), raw_body.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                frappe.log_error("Signature mismatch", "Razorpay Webhook - Invalid Signature")
                return {"status": "error", "message": "Invalid signature"}
        else:
            frappe.log_error(
                "webhook_secret not configured in Razorpay Settings — skipping signature check",
                "Razorpay Webhook Warning",
            )

        event = json.loads(raw_body)
        event_type = event.get("event", "")
        payload = event.get("payload", {})

        if event_type == "payment.authorized":
            _handle_payment_authorized(payload)
        elif event_type == "payment.captured":
            _handle_payment_captured(payload)
        elif event_type == "payment.failed":
            _handle_payment_failed(payload)
        elif event_type in ("refund.created", "refund.processed"):
            frappe.log_error(
                json.dumps(payload), f"Razorpay Webhook - {event_type} (log only)"
            )

        return {"status": "success"}

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Razorpay Webhook Error")
        return {"status": "error"}


def _handle_payment_authorized(payload):
    payment_entity = payload.get("payment", {}).get("entity", {})
    rz_order_id = payment_entity.get("order_id")
    rz_payment_id = payment_entity.get("id")

    entry_name = frappe.db.get_value(
        "Razorpay Payment Entry", {"razorpay_order_id": rz_order_id}, "name"
    )
    if not entry_name:
        return
    frappe.db.set_value(
        "Razorpay Payment Entry",
        entry_name,
        {"status": "AUTHORIZED", "razorpay_payment_id": rz_payment_id},
    )
    frappe.db.commit()


def _handle_payment_captured(payload):
    payment_entity = payload.get("payment", {}).get("entity", {})
    rz_order_id = payment_entity.get("order_id")
    rz_payment_id = payment_entity.get("id")

    entry_name = frappe.db.get_value(
        "Razorpay Payment Entry", {"razorpay_order_id": rz_order_id}, "name"
    )
    if not entry_name:
        return

    rpe = frappe.get_doc("Razorpay Payment Entry", entry_name)
    rpe.razorpay_payment_id = rz_payment_id
    rpe.status = "CAPTURED"
    rpe.razorpay_response = json.dumps(payment_entity)
    rpe.save(ignore_permissions=True)

    if not rpe.payment_entry:
        create_payment_entry_from_razorpay(rpe)


def _handle_payment_failed(payload):
    payment_entity = payload.get("payment", {}).get("entity", {})
    rz_order_id = payment_entity.get("order_id")
    error = payment_entity.get("error_description", "")

    entry_name = frappe.db.get_value(
        "Razorpay Payment Entry", {"razorpay_order_id": rz_order_id}, "name"
    )
    if not entry_name:
        return
    frappe.db.set_value(
        "Razorpay Payment Entry",
        entry_name,
        {"status": "FAILED", "notes": f"Payment failed: {error}"},
    )
    frappe.db.commit()
