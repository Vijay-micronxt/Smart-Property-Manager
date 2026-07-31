from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils import cint

from property_core.property_core.api.ecommerce.mswipe_integration import (
    MSWIPE_ATTEMPT_BY_TRANSID_PREFIX,
    MSWIPE_RETURN_URL_CACHE_PREFIX,
    MswipeGateway,
    create_payment_entry_from_mswipe,
)
from property_core.property_core.api.ecommerce.razorpay_integration import (
    create_sales_invoice_from_order,
)


def _respond(return_url, status, order_id=None, message=None, **extra_data):
    if return_url:
        params = {"status": status}
        if order_id:
            params["order_id"] = order_id
        if message:
            params["message"] = message
        params.update(extra_data)
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = return_url + "?" + urlencode(params)
        return

    if status in ("TXN_FAILURE", "UNKNOWN", "error"):
        return {"status": 400, "error": message or status}
    return {"status": 200, "data": {"order_id": order_id, "status": status, **extra_data}}


@frappe.whitelist(allow_guest=True)
def handle_mswipe_callback():
    order_id = None
    return_url = None

    try:
        trans_id = frappe.local.form_dict.get("encIpgId") or frappe.local.form_dict.get("TransID")

        if not trans_id:
            frappe.log_error(title="Mswipe Callback Error", message="encIpgId missing in Mswipe callback")
            return _respond(None, "error", message="Missing transaction ID")

        # Look up order_id
        cached_attempt = frappe.cache().get_value(MSWIPE_ATTEMPT_BY_TRANSID_PREFIX + trans_id)
        if cached_attempt:
            order_id = cached_attempt.get("order_id")
        else:
            order_id = frappe.db.get_value(
                "Mswipe Payment Entry", {"mswipe_trans_id": trans_id}, "mswipe_order_id"
            )

        if not order_id:
            frappe.log_error(title="Mswipe Callback Error", message=f"No order found for trans_id {trans_id}")
            return _respond(None, "error", message="Order not found")

        # Look up return_url
        cached_url = frappe.cache().get_value(MSWIPE_RETURN_URL_CACHE_PREFIX + order_id)
        if cached_url:
            return_url = cached_url
        else:
            return_url = frappe.db.get_value(
                "Mswipe Payment Entry", {"mswipe_order_id": order_id}, "return_url"
            )

        entry_name = frappe.db.get_value(
            "Mswipe Payment Entry", {"mswipe_order_id": order_id}, "name"
        )
        if not entry_name:
            frappe.log_error(
                title="Mswipe Callback Error",
                message=f"Mswipe Payment Entry not found for order {order_id}",
            )
            return _respond(return_url, "error", order_id=order_id, message="Entry not found")

        mswipe_entry = frappe.get_doc("Mswipe Payment Entry", entry_name)

        # Server-to-server status check — never trust callback params alone
        gateway = MswipeGateway()
        row = gateway.check_transaction_status(trans_id)

        payment_status = cint(row.get("Payment_Status"))

        if payment_status != 1:
            status_map = {0: "TXN_FAILURE", 2: "PENDING"}
            label = status_map.get(payment_status, "UNKNOWN")
            frappe.log_error(
                title="Mswipe Callback - Non-success",
                message=f"Mswipe payment not successful for trans_id {trans_id}: status={payment_status}",
            )
            mswipe_entry.db_set("status", "FAILED" if payment_status == 0 else "PENDING")
            return _respond(return_url, label, order_id=order_id)

        txn_id = row.get("IPG_ID")
        if not txn_id:
            frappe.log_error(
                title="Mswipe Callback Warning",
                message=f"IPG_ID missing in Mswipe status response for trans_id {trans_id}; falling back to stored txn_id",
            )
            txn_id = mswipe_entry.mswipe_txn_id

        # Idempotency guard 1: PE already linked on entry
        if mswipe_entry.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", mswipe_entry.payment_entry, "docstatus")
            if pe_status == 1:
                return _respond(
                    return_url, "TXN_SUCCESS", order_id=order_id, is_duplicate=True,
                    payment_entry=mswipe_entry.payment_entry,
                )

        # Idempotency guard 2: PE with matching reference_no already submitted
        existing_pe = frappe.db.get_value(
            "Payment Entry", {"reference_no": txn_id, "docstatus": 1}, "name"
        )
        if existing_pe:
            mswipe_entry.db_set("payment_entry", existing_pe)
            return _respond(
                return_url, "TXN_SUCCESS", order_id=order_id, is_duplicate=True,
                payment_entry=existing_pe,
            )

        # Create SI if not exists
        si_name = create_sales_invoice_from_order(order_id)

        # Update Mswipe Payment Entry
        customer = frappe.db.get_value("Sales Invoice", si_name, "customer")
        amount = float(row.get("TxnAmount") or row.get("Amount") or mswipe_entry.amount or 0)

        mswipe_entry.sales_invoice = si_name
        mswipe_entry.customer = customer
        mswipe_entry.mswipe_txn_id = txn_id
        mswipe_entry.amount = amount
        mswipe_entry.status = "SUCCESS"
        mswipe_entry.verified = 1
        mswipe_entry.mswipe_response = str(row)
        mswipe_entry.save(ignore_permissions=True)

        # Create ERPNext Payment Entry
        create_payment_entry_from_mswipe(mswipe_entry)

        # Single commit for the entire confirm-and-credit sequence
        frappe.db.commit()

        return _respond(
            return_url, "TXN_SUCCESS", order_id=order_id,
            payment_entry=mswipe_entry.payment_entry,
            sales_invoice=si_name,
        )

    except Exception:
        frappe.log_error(title="Mswipe Callback Fatal Error", message=frappe.get_traceback())
        return _respond(return_url, "error", order_id=order_id, message="Internal error")
