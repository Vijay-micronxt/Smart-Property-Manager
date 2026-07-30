import hashlib
import json
import re
import base64
from datetime import datetime

import frappe
import requests
from frappe import _

# pycryptodome — must be installed: pip install pycryptodome
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_IV = "@@@@&&&&####$$$$"  # Paytm's fixed IV — public constant


# ─── Crypto helpers ───────────────────────────────────────────────────────────

def _random_salt(length=4):
    import random
    import string
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _aes_encrypt(plain_text, key):
    cipher = AES.new(key.encode(), AES.MODE_CBC, _IV.encode())
    padded = pad(plain_text.encode(), AES.block_size)
    encrypted = cipher.encrypt(padded)
    return base64.b64encode(encrypted).decode()


def generate_paytm_signature(body_dict, merchant_key):
    key_bytes = merchant_key.encode()
    if len(key_bytes) not in (16, 24, 32):
        frappe.throw(
            _("Paytm merchant key must be 16, 24, or 32 bytes; got {0}").format(len(key_bytes))
        )
    body_string = json.dumps(body_dict, separators=(",", ":"))
    salt = _random_salt(4)
    hashed = hashlib.sha256((body_string + "|" + salt).encode()).hexdigest()
    return _aes_encrypt(hashed + salt, merchant_key)


# ─── Lookup helpers ────────────────────────────────────────────────────────────

def _last10_digits(phone):
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _find_customer_by_phone(phone_key):
    if not phone_key:
        return None

    # 1. Direct match on Customer.mobile_no
    result = frappe.db.sql(
        "SELECT name FROM `tabCustomer` WHERE mobile_no LIKE %s LIMIT 1",
        f"%{phone_key}%",
    )
    if result:
        return result[0][0]

    # 2. Via Contact Phone → Contact → Dynamic Link → Customer
    contact_name = frappe.db.sql(
        """
        SELECT cp.parent FROM `tabContact Phone` cp
        JOIN `tabContact` c ON c.name = cp.parent
        WHERE cp.phone LIKE %s
        LIMIT 1
        """,
        f"%{phone_key}%",
    )
    if not contact_name:
        return None

    contact = contact_name[0][0]
    customer = frappe.db.get_value(
        "Dynamic Link",
        {"parent": contact, "link_doctype": "Customer", "parenttype": "Contact"},
        "link_name",
    )
    return customer or None


# ─── Internal link creator (shared) ───────────────────────────────────────────

def _create_paytm_link(merchant_id, merchant_key, order_id, amount, customer,
                        callback_url, is_staging, allow_partial=False, min_partial_amount=None):
    base_url = (
        "https://securestage.paytmpayments.com" if is_staging else "https://securegw.paytm.com"
    )

    link_name = re.sub(r"[^A-Za-z0-9]", "", customer)[:50] or "Customer"
    link_description = f"Order - {customer}"[:30]
    link_type = "PARTIAL" if allow_partial else "FIXED"

    request_body = {
        "mid": merchant_id,
        "orderId": order_id,
        "amount": f"{float(amount):.2f}",
        "linkType": link_type,
        "linkDescription": link_description,
        "linkName": link_name,
        "callbackUrl": callback_url,
        "sendSms": False,
        "sendEmail": False,
    }

    if allow_partial and min_partial_amount is not None:
        request_body["minPaymentAmount"] = f"{float(min_partial_amount):.2f}"

    signature = generate_paytm_signature(request_body, merchant_key)
    payload = {
        "body": request_body,
        "head": {"tokenType": "AES", "signature": signature},
    }

    resp = requests.post(f"{base_url}/link/create", json=payload, timeout=30)
    resp.raise_for_status()
    response_data = resp.json()

    body = response_data.get("body", {})
    link_url = body.get("link") or body.get("shortUrl")
    if not link_url:
        frappe.log_error(json.dumps(response_data), "Paytm Link Creation Failed")
        frappe.throw(_("Paytm did not return a payment link. Check Error Log for details."))

    return link_url


# ─── Whitelisted function 1: ecommerce checkout ───────────────────────────────

@frappe.whitelist()
def generate_ecommerce_payment_link(so_name, amount=None, allow_partial=0, min_partial_amount=None):
    so = frappe.get_doc("Sales Order", so_name)
    if so.docstatus != 1:
        frappe.throw(_("Sales Order must be submitted before generating a payment link"))
    if so.billing_status == "Fully Billed":
        frappe.throw(_("Sales Order is already fully billed"))

    if not frappe.db.exists("DocType", "Paytm Settings"):
        frappe.throw(
            _("Paytm Settings doctype not found in the database. "
              "Run `bench migrate` on the server to install it, "
              "then fill in the credentials at /app/paytm-settings.")
        )
    settings = frappe.get_single("Paytm Settings")
    merchant_id = settings.merchant_id
    merchant_key = _get_merchant_key(settings)
    is_staging = bool(settings.staging)

    # Use caller-supplied amount (e.g. an instalment); fall back to SO grand total
    link_amount = float(amount) if amount else float(so.grand_total)
    if link_amount <= 0:
        frappe.throw(_("Amount must be greater than zero"))
    if link_amount > float(so.grand_total):
        frappe.throw(
            _("Amount {0} exceeds Sales Order total {1}").format(link_amount, so.grand_total)
        )

    allow_partial = bool(int(allow_partial or 0))
    customer = so.customer
    so_clean = re.sub(r"[^A-Za-z0-9]", "", so_name)[:16]
    order_id = "EC" + so_clean + datetime.now().strftime("%Y%m%d%H%M%S")

    frappe.cache().set_value(
        f"paytm_order:{order_id}",
        {
            "flow": "ecommerce",
            "so_name": so_name,
            "customer": customer,
            "amount": link_amount,
            "allow_partial": allow_partial,
        },
        expires_in_sec=7 * 24 * 3600,
    )

    callback_url = frappe.utils.get_url(
        "/api/method/property_core.property_core.api.paytm_payment_webhook.handle_link_payment"
    )

    link_url = _create_paytm_link(
        merchant_id=merchant_id,
        merchant_key=merchant_key,
        order_id=order_id,
        amount=link_amount,
        customer=customer,
        callback_url=callback_url,
        is_staging=is_staging,
        allow_partial=allow_partial,
        min_partial_amount=float(min_partial_amount) if min_partial_amount else None,
    )

    message = (
        f"💳 *Payment Link*\n"
        f"Order: {so_name}\n"
        f"Amount: ₹{link_amount:,.2f}"
        + (" (partial accepted)" if allow_partial else "") + "\n\n"
        f"Pay securely here:\n{link_url}\n\n"
        f"This link is valid for a limited time."
    )
    return {"link": link_url, "amount": link_amount, "order_id": order_id, "message": message}


# ─── Whitelisted function 2: WhatsApp dealer dues ─────────────────────────────

@frappe.whitelist(allow_guest=True)
def generate_payment_link():
    try:
        phone = frappe.form_dict.get("phone")
        if not phone:
            try:
                body = frappe.request.get_json(force=True) or {}
                phone = body.get("phone") or (body.get("lead") or {}).get("phone")
            except Exception:
                pass

        phone_key = _last10_digits(phone)
        if not phone_key:
            frappe.response["message"] = {
                "status": "error",
                "message": "A valid phone number is required",
            }
            return

        customer = _find_customer_by_phone(phone_key)
        if not customer:
            frappe.response["message"] = {
                "status": "error",
                "message": f"No customer found for phone ending in {phone_key}",
            }
            return

        outstanding_invoices = frappe.get_all(
            "Sales Invoice",
            filters={"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
            fields=["outstanding_amount"],
        )
        total_due = sum(float(inv.outstanding_amount) for inv in outstanding_invoices)

        if total_due <= 0:
            frappe.response["message"] = {
                "status": "ok",
                "amount": 0,
                "message": f"No outstanding dues for customer {customer}",
            }
            return

        settings = frappe.get_single("Paytm Settings")
        merchant_id = settings.merchant_id
        merchant_key = _get_merchant_key(settings)
        is_staging = bool(settings.staging)

        cust_clean = customer[:12].replace(" ", "").replace("-", "")
        order_id = "WA" + cust_clean + datetime.now().strftime("%Y%m%d%H%M%S")

        frappe.cache().set_value(
            f"paytm_order:{order_id}",
            {"customer": customer, "amount": total_due},
            expires_in_sec=7 * 24 * 3600,
        )

        callback_url = frappe.utils.get_url(
            "/api/method/property_core.property_core.api.paytm_payment_webhook.handle_link_payment"
        )

        link_url = _create_paytm_link(
            merchant_id=merchant_id,
            merchant_key=merchant_key,
            order_id=order_id,
            amount=total_due,
            customer=customer,
            callback_url=callback_url,
            is_staging=is_staging,
            allow_partial=True,  # dealer dues: customer may pay any portion
        )

        message = (
            f"💳 *Payment Link*\n"
            f"Customer: {customer}\n"
            f"Total Outstanding: ₹{total_due:,.2f}\n\n"
            f"Pay securely here:\n{link_url}\n\n"
            f"This link is valid for a limited time."
        )
        frappe.response["message"] = {
            "status": "ok",
            "amount": total_due,
            "link": link_url,
            "order_id": order_id,
            "message": message,
        }

    except Exception:
        frappe.log_error(frappe.get_traceback(), "generate_payment_link error")
        frappe.response["message"] = {"status": "error", "message": "Failed to generate link"}


# ─── Internal ─────────────────────────────────────────────────────────────────

def _get_merchant_key(settings):
    try:
        return settings.get_password("merchant_key")
    except Exception:
        return frappe.db.get_value("Paytm Settings", None, "merchant_key")
