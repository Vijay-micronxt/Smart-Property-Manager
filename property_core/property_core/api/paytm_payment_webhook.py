import base64
import hashlib
import json

import frappe
import requests
from frappe import _

# pycryptodome — must be installed: pip install pycryptodome
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

_IV = "@@@@&&&&####$$$$"  # Paytm's fixed IV — public constant


# ─── Crypto helpers ───────────────────────────────────────────────────────────

def _aes_decrypt(cipher_text, key):
    raw = base64.b64decode(cipher_text)
    cipher = AES.new(key.encode(), AES.MODE_CBC, _IV.encode())
    decrypted = unpad(cipher.decrypt(raw), AES.block_size)
    return decrypted.decode()


def _verify_signature(body_dict, signature, merchant_key):
    try:
        decrypted = _aes_decrypt(signature, merchant_key)
        # Last 4 chars are the salt
        salt = decrypted[-4:]
        recovered_hash = decrypted[:-4]
        body_string = json.dumps(body_dict, separators=(",", ":"))
        expected = hashlib.sha256((body_string + "|" + salt).encode()).hexdigest()
        return recovered_hash == expected
    except Exception:
        frappe.log_error(title="Paytm Signature Verification Error", message=frappe.get_traceback())
        return False


def _get_merchant_key(settings):
    try:
        return (settings.get_password("merchant_key") or "").strip()
    except Exception:
        return (frappe.db.get_value("Paytm Settings", "Paytm Settings", "merchant_key") or "").strip()


def _confirm_order_status(merchant_id, merchant_key, order_id, base_url):
    from property_core.property_core.api.paytm_payment_link import generate_paytm_signature

    request_body = {"mid": merchant_id, "orderId": order_id}
    signature = generate_paytm_signature(request_body, merchant_key)
    payload = {
        "body": request_body,
        "head": {"tokenType": "AES", "signature": signature},
    }
    resp = requests.post(
        f"{base_url}/v3/order/status",
        data=json.dumps(payload, separators=(",", ":")),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("body", {})


# ─── Payment Entry builder ────────────────────────────────────────────────────

def _build_payment_entry(customer, amount, txn_id, order_id, settings, si_name=None, system_user=None):
    payment_account = settings.payment_account
    if not payment_account:
        frappe.throw(_("Paytm Settings: payment_account is required"))

    mode_of_payment = settings.mode_of_payment or "Paytm"
    company = frappe.db.get_value("Account", payment_account, "company")
    paid_from = frappe.get_cached_value("Company", company, "default_receivable_account")
    company_currency = frappe.get_cached_value("Company", company, "default_currency") or "INR"
    paid_from_currency = frappe.db.get_value("Account", paid_from, "account_currency") or company_currency
    paid_to_currency = frappe.db.get_value("Account", payment_account, "account_currency") or company_currency

    effective_user = system_user or "Administrator"
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.company = company
    pe.mode_of_payment = mode_of_payment
    pe.paid_from = paid_from
    pe.paid_to = payment_account
    pe.paid_from_account_currency = paid_from_currency
    pe.paid_to_account_currency = paid_to_currency
    pe.source_exchange_rate = 1.0
    pe.target_exchange_rate = 1.0
    pe.paid_amount = float(amount)
    pe.received_amount = float(amount)
    pe.base_paid_amount = float(amount)
    pe.base_received_amount = float(amount)
    pe.reference_no = txn_id
    pe.reference_date = frappe.utils.today()
    pe.remarks = f"Paytm order: {order_id}"

    if si_name:
        pe.append(
            "references",
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": si_name,
                "allocated_amount": float(amount),
            },
        )
    else:
        # Allocate across outstanding invoices oldest-first
        invoices = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
            fields=["name", "outstanding_amount"],
            order_by="posting_date asc",
        )
        remaining = float(amount)
        for inv in invoices:
            if remaining <= 0:
                break
            alloc = min(remaining, float(inv.outstanding_amount))
            pe.append(
                "references",
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": inv.name,
                    "allocated_amount": alloc,
                },
            )
            remaining -= alloc

    pe.owner = effective_user
    pe.flags.ignore_permissions = True
    pe.insert()
    pe.submit()
    return pe.name


# ─── Flow handlers ────────────────────────────────────────────────────────────

def _handle_dealer_dues(cached, txn_amount, txn_id, order_id, settings):
    customer = cached["customer"]
    system_user = getattr(settings, "system_user", None) or "Administrator"
    pe_name = _build_payment_entry(customer, txn_amount, txn_id, order_id, settings, system_user=system_user)
    return {"payment_entry": pe_name}


def _handle_ecommerce(cached, txn_amount, txn_id, order_id, settings):
    so_name = cached["so_name"]
    customer = cached.get("customer")
    system_user = getattr(settings, "system_user", None) or "Administrator"

    # Idempotency: check if SI already exists for this SO
    existing_si = frappe.db.sql(
        """
        SELECT sii.parent FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.sales_order = %s AND si.docstatus = 1
        LIMIT 1
        """,
        so_name,
    )
    si_name = existing_si[0][0] if existing_si else None

    if not si_name:
        from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
        si_doc = frappe.get_doc(make_sales_invoice(so_name, ignore_permissions=True))
        si_doc.flags.ignore_permissions = True
        si_doc.owner = system_user
        si_doc.insert()
        si_doc.submit()
        si_name = si_doc.name
        customer = customer or si_doc.customer

    if not customer:
        customer = frappe.db.get_value("Sales Invoice", si_name, "customer")

    pe_name = _build_payment_entry(customer, txn_amount, txn_id, order_id, settings, si_name=si_name, system_user=system_user)
    return {"sales_invoice": si_name, "payment_entry": pe_name}


# ─── Webhook endpoint ─────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def handle_link_payment():
    # Always return HTTP 200 — Paytm retries on non-200, causing duplicate PEs
    try:
        data = frappe.request.get_json(force=True) or {}
        body = data.get("body", {})
        head = data.get("head", {})
        order_id = body.get("orderId") or data.get("orderId")
        signature = head.get("signature")

        if not order_id:
            frappe.log_error(title="Paytm handle_link_payment - missing orderId", message=str(data))
            frappe.response["message"] = {"status": "error", "reason": "missing_order_id"}
            return

        settings = frappe.get_single("Paytm Settings")
        merchant_id = settings.merchant_id
        merchant_key = _get_merchant_key(settings)
        is_staging = bool(settings.staging)
        base_url = (
            "https://securestage.paytmpayments.com" if is_staging else "https://securegw.paytm.com"
        )

        if signature:
            if not _verify_signature(body, signature, merchant_key):
                frappe.log_error(title="Paytm handle_link_payment - invalid signature", message=str(data))
                frappe.response["message"] = {"status": "error", "reason": "invalid_signature"}
                return

        # Always confirm server-to-server before crediting
        status_body = _confirm_order_status(merchant_id, merchant_key, order_id, base_url)
        result_info = status_body.get("resultInfo", {})

        if result_info.get("resultStatus") != "TXN_SUCCESS":
            frappe.response["message"] = {
                "status": "pending",
                "txn_status": result_info.get("resultStatus"),
                "message": result_info.get("resultMsg"),
            }
            return

        txn_amount_raw = status_body.get("txnAmount", 0)
        txn_amount = float(
            txn_amount_raw.get("value", 0) if isinstance(txn_amount_raw, dict) else (txn_amount_raw or 0)
        )
        txn_id = status_body.get("txnId") or status_body.get("txnToken")

        # Idempotency: check by reference_no
        if frappe.db.exists("Payment Entry", {"reference_no": txn_id}):
            frappe.response["message"] = {"status": "ok", "reason": "already_processed"}
            return

        cached = frappe.cache().get_value(f"paytm_order:{order_id}")
        if not cached:
            frappe.log_error(
                title="Paytm handle_link_payment - cache miss",
                message=f"paytm_order:{order_id} not in cache",
            )
            frappe.response["message"] = {"status": "error", "reason": "order_not_found"}
            return

        flow = cached.get("flow", "dealer_dues")
        if flow == "ecommerce":
            result = _handle_ecommerce(cached, txn_amount, txn_id, order_id, settings)
        else:
            result = _handle_dealer_dues(cached, txn_amount, txn_id, order_id, settings)

        frappe.log_error(
            title="Paytm handle_link_payment - Success",
            message=f"order_id={order_id} txn_id={txn_id} result={result}",
        )
        frappe.response["message"] = {"status": "ok", **result}

    except Exception:
        frappe.log_error(title="Paytm handle_link_payment error", message=frappe.get_traceback())
        frappe.response["message"] = {"status": "error"}
