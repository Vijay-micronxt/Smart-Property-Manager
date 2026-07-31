import hashlib
import hmac
import json

import frappe
from frappe import _

from property_core.property_core.api.ecommerce.razorpay_integration import (
    RazorpayGateway,
    create_payment_entry_from_razorpay,
    create_sales_invoice_from_order,
)


@frappe.whitelist(allow_guest=True)
def handle_razorpay_webhook():
    try:
        raw_body = frappe.request.get_data(as_text=True)
        signature = frappe.request.headers.get("X-Razorpay-Signature", "")

        settings = frappe.get_single("Razorpay Settings")
        webhook_secret = settings.get_password("webhook_secret") if getattr(settings, "webhook_secret", None) else None

        if webhook_secret:
            expected = hmac.new(
                webhook_secret.encode(), raw_body.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, signature):
                frappe.log_error(title="Razorpay Webhook - Invalid Signature", message="Signature mismatch")
                return {"status": "error", "message": "Invalid signature"}
        else:
            frappe.log_error(
                title="Razorpay Webhook Warning",
                message="webhook_secret not configured in Razorpay Settings — skipping signature check",
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
                title=f"Razorpay Webhook - {event_type} (log only)",
                message=json.dumps(payload),
            )

        return {"status": "success"}

    except Exception:
        frappe.log_error(title="Razorpay Webhook Error", message=frappe.get_traceback())
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

    # Create Sales Invoice if not already linked
    if not rpe.sales_invoice:
        # The original order_id (SO name) is stored in the Transaction Log receipt
        original_order_id = frappe.db.get_value(
            "Razorpay Transaction Log", {"razorpay_order_id": rz_order_id}, "order_id"
        )
        if not original_order_id:
            # Fallback: Razorpay stores order_id in the receipt field of the order notes
            notes = payment_entity.get("notes") or {}
            original_order_id = notes.get("order_id")

        if original_order_id:
            try:
                si_name = create_sales_invoice_from_order(original_order_id)
                rpe.db_set("sales_invoice", si_name)
                rpe.sales_invoice = si_name
            except Exception:
                frappe.log_error(
                    title=f"Razorpay webhook - SI creation failed for order {original_order_id}",
                    message=frappe.get_traceback(),
                )
        else:
            frappe.log_error(
                title="Razorpay Webhook - Missing order_id",
                message=f"Cannot create SI: original order_id not found for Razorpay order {rz_order_id}",
            )

    if not rpe.payment_entry and rpe.sales_invoice:
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
