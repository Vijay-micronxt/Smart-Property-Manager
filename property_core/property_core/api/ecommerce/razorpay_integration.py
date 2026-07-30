import hashlib
import hmac
import json

import frappe
import requests
from frappe import _


class RazorpayGateway:
    def __init__(self):
        if not frappe.db.exists("DocType", "Razorpay Settings"):
            frappe.throw(
                _("Razorpay Settings doctype not found in the database. "
                  "Run `bench migrate` on the server to install it, "
                  "then fill in the credentials at /app/razorpay-settings.")
            )
        settings = frappe.get_single("Razorpay Settings")
        self.key_id = settings.api_key
        self.key_secret = settings.get_password("api_secret") if settings.api_secret else None
        self.webhook_secret = settings.get_password("webhook_secret") if getattr(settings, "webhook_secret", None) else None
        self.system_user = settings.system_user
        self.base_url = "https://api.razorpay.com/v1"

        if not self.key_id or not self.key_secret:
            frappe.throw(_("Razorpay API Key and Secret must be configured in Razorpay Settings"))

    def create_order(self, amount, currency, order_id, customer_email=None,
                     customer_phone=None, notes=None):
        amount_paise = int(float(amount))  # caller passes paise already
        payload = {
            "amount": amount_paise,
            "currency": currency or "INR",
            "receipt": order_id,
            "notes": notes or {"order_id": order_id},
        }
        response = self._make_request("POST", "/orders", payload)
        self._log_transaction(
            order_id=order_id,
            razorpay_order_id=response.get("id"),
            amount=amount,
            currency=currency or "INR",
            status=response.get("status", "created"),
            response_json=json.dumps(response),
        )
        return response

    def create_payment_link(self, amount, currency, customer_email, customer_phone,
                             description, order_id, callback_url=None, expires_by=None):
        amount_paise = int(float(amount))  # caller passes paise already
        payload = {
            "amount": amount_paise,
            "currency": currency or "INR",
            "accept_partial": True,
            "first_min_partial_amount": 100,
            "description": description,
            "reference_id": order_id,
            "customer": {
                "name": order_id,
                "email": customer_email or "",
                "contact": customer_phone or "",
            },
        }
        if callback_url:
            payload["notify"] = {"sms": True, "email": True}
            payload["callback_url"] = callback_url
            payload["callback_method"] = "get"
        if expires_by:
            payload["expire_by"] = expires_by
        return self._make_request("POST", "/payment_links", payload)

    def verify_payment(self, razorpay_payment_id, razorpay_order_id, razorpay_signature):
        body = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected = hmac.new(
            self.key_secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, razorpay_signature)

    def fetch_payment(self, payment_id):
        return self._make_request("GET", f"/payments/{payment_id}", None)

    def fetch_order(self, order_id):
        return self._make_request("GET", f"/orders/{order_id}", None)

    def refund_payment(self, payment_id, amount, notes=None):
        payload = {"amount": int(float(amount) * 100)}
        if notes:
            payload["notes"] = notes
        return self._make_request("POST", f"/payments/{payment_id}/refund", payload)

    def _make_request(self, method, endpoint, payload):
        url = self.base_url + endpoint
        try:
            if method == "GET":
                resp = requests.get(url, auth=(self.key_id, self.key_secret), timeout=30)
            else:
                resp = requests.post(
                    url, json=payload, auth=(self.key_id, self.key_secret), timeout=30
                )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            try:
                err = e.response.json()
            except Exception:
                err = e.response.text
            frappe.log_error(str(err), "Razorpay API Error")
            frappe.throw(_("Razorpay API error: {0}").format(str(err)))
        except requests.exceptions.RequestException as e:
            frappe.log_error(str(e), "Razorpay Request Error")
            frappe.throw(_("Razorpay connection error: {0}").format(str(e)))

    def _log_transaction(self, **kwargs):
        doc = frappe.new_doc("Razorpay Transaction Log")
        doc.name = frappe.generate_hash(length=10)
        for k, v in kwargs.items():
            doc.set(k, v)
        doc.insert(ignore_permissions=True)
        frappe.db.commit()


# ─── Whitelisted endpoints ────────────────────────────────────────────────────

@frappe.whitelist()
def order_payment(order_id, amount, store_id=None, owner_id=None, payment_provider_id=None):
    try:
        gateway = RazorpayGateway()
        order_doc = frappe.get_doc(_get_doctype(order_id), order_id)
        notes = {"order_id": order_id, "store_id": store_id or ""}
        rz_order = gateway.create_order(
            amount=amount,
            currency="INR",
            order_id=order_id,
            customer_email=getattr(order_doc, "contact_email", None),
            customer_phone=getattr(order_doc, "contact_mobile", None),
            notes=notes,
        )
        _ensure_razorpay_payment_entry(rz_order["id"], order_doc, amount)
        return {
            "status": 200,
            "data": {
                "order": {
                    "id": rz_order["id"],
                    "amount": float(rz_order["amount"]) / 100,
                    "currency": rz_order.get("currency", "INR"),
                    "receipt": rz_order.get("receipt"),
                    "transactionId": rz_order["id"],
                }
            },
            "key": gateway.key_id,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Razorpay order_payment error")
        return {"status": 400, "error": str(e)}


@frappe.whitelist()
def verify_payment_signature(razorpay_payment_id, razorpay_order_id, razorpay_signature):
    gateway = RazorpayGateway()
    if not gateway.verify_payment(razorpay_payment_id, razorpay_order_id, razorpay_signature):
        frappe.throw(_("Invalid payment signature"))

    payment = gateway.fetch_payment(razorpay_payment_id)
    payment_status = payment.get("status", "").upper()

    entry_name = frappe.db.get_value(
        "Razorpay Payment Entry", {"razorpay_order_id": razorpay_order_id}, "name"
    )
    if entry_name and payment_status in ("CAPTURED", "AUTHORIZED"):
        rpe = frappe.get_doc("Razorpay Payment Entry", entry_name)
        if not rpe.payment_entry:
            create_payment_entry_from_razorpay(rpe)

    return {
        "success": True,
        "message": "Payment verified",
        "payment_status": payment_status,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_order_id": razorpay_order_id,
    }


@frappe.whitelist()
def capture_payment(order_id, payment_token, store_id=None, party=None,
                    payment_provider_id=None, transaction_id=None, owner_id=None):
    try:
        gateway = RazorpayGateway()
        payment = gateway.fetch_payment(payment_token)
        payment_status = payment.get("status", "").upper()

        if payment_status not in ("CAPTURED", "AUTHORIZED"):
            return {
                "status": 400,
                "error": f"Payment not captured. Status: {payment_status}",
            }

        rz_order_id = payment.get("order_id")
        rz_order = gateway.fetch_order(rz_order_id)
        original_order_id = (rz_order.get("notes") or {}).get("order_id", order_id)
        amount = float(payment.get("amount", 0)) / 100

        existing_name = frappe.db.get_value(
            "Razorpay Payment Entry", {"razorpay_order_id": rz_order_id}, "name"
        )
        if existing_name:
            rpe = frappe.get_doc("Razorpay Payment Entry", existing_name)
            if rpe.payment_entry:
                return {
                    "status": 200,
                    "is_duplicate": True,
                    "data": {
                        "payment_id": payment_token,
                        "order_id": rz_order_id,
                        "amount": amount,
                        "currency": payment.get("currency", "INR"),
                        "status": rpe.status,
                        "payment_entry": rpe.payment_entry,
                        "sales_invoice": rpe.sales_invoice,
                    },
                }
            create_payment_entry_from_razorpay(rpe)
            return {
                "status": 200,
                "is_duplicate": False,
                "data": {
                    "payment_id": payment_token,
                    "order_id": rz_order_id,
                    "amount": amount,
                    "currency": payment.get("currency", "INR"),
                    "status": "COMPLETED",
                    "payment_entry": rpe.payment_entry,
                    "sales_invoice": rpe.sales_invoice,
                },
            }

        si_name = create_sales_invoice_from_order(original_order_id)
        order_doc = frappe.get_doc(_get_doctype(original_order_id), original_order_id)

        rpe = frappe.new_doc("Razorpay Payment Entry")
        rpe.name = frappe.generate_hash(length=10)
        rpe.sales_invoice = si_name
        rpe.customer = getattr(order_doc, "customer", None)
        rpe.razorpay_order_id = rz_order_id
        rpe.razorpay_payment_id = payment_token
        rpe.amount = amount
        rpe.currency = payment.get("currency", "INR")
        rpe.status = "CAPTURED"
        rpe.payment_method = "razorpay"
        rpe.razorpay_response = json.dumps(payment)
        rpe.insert(ignore_permissions=True)

        create_payment_entry_from_razorpay(rpe)

        return {
            "status": 200,
            "is_duplicate": False,
            "data": {
                "payment_id": payment_token,
                "order_id": rz_order_id,
                "amount": amount,
                "currency": payment.get("currency", "INR"),
                "status": "COMPLETED",
                "payment_entry": rpe.payment_entry,
                "sales_invoice": si_name,
            },
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Razorpay capture_payment error")
        return {"status": 400, "error": str(e)}


# ─── Shared (non-whitelisted) helpers ─────────────────────────────────────────

def create_sales_invoice_from_order(order_name):
    """Gateway-agnostic. Imported by mswipe_webhooks too."""
    doctype = _get_doctype(order_name)
    so_name = order_name

    if doctype == "Quotation":
        existing_so = frappe.db.get_value(
            "Sales Order", {"quotation": order_name, "docstatus": ["!=", 2]}, "name"
        )
        if existing_so:
            so_name = existing_so
        else:
            from erpnext.selling.doctype.quotation.quotation import make_sales_order
            so = frappe.get_doc(make_sales_order(order_name))
            so.flags.ignore_permissions = True
            so.insert()
            so.submit()
            so_name = so.name

    existing_si = frappe.db.get_value(
        "Sales Invoice", {"sales_order": so_name, "docstatus": ["!=", 2]}, "name"
    )
    if existing_si:
        return existing_si

    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    si_doc = frappe.get_doc(make_sales_invoice(so_name))
    si_doc.flags.ignore_permissions = True
    try:
        gateway = RazorpayGateway()
        si_doc.owner = gateway.system_user or frappe.session.user
    except Exception:
        si_doc.owner = frappe.session.user
    si_doc.insert()
    si_doc.submit()

    if frappe.db.has_column("Sales Order", "custom_link_sales_invoice"):
        frappe.db.set_value("Sales Order", so_name, "custom_link_sales_invoice", si_doc.name)

    return si_doc.name


def create_payment_entry_from_razorpay(razorpay_payment_entry):
    si_name = razorpay_payment_entry.sales_invoice
    if not si_name:
        frappe.throw(_("Razorpay Payment Entry has no linked Sales Invoice"))

    si = frappe.get_doc("Sales Invoice", si_name)
    company = si.company

    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": "Razorpay", "company": company},
        "default_account",
    )
    if not mop_account:
        frappe.throw(
            _("Configure default account for 'Razorpay' Mode of Payment for company {0}").format(company)
        )

    paid_from = frappe.get_cached_value("Company", company, "default_receivable_account")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = si.customer
    pe.company = company
    pe.mode_of_payment = "Razorpay"
    pe.paid_from = paid_from
    pe.paid_to = mop_account
    pe.paid_amount = razorpay_payment_entry.amount
    pe.received_amount = razorpay_payment_entry.amount
    pe.reference_no = (
        razorpay_payment_entry.razorpay_payment_id
        or razorpay_payment_entry.razorpay_order_id
    )
    pe.reference_date = frappe.utils.today()
    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": si_name,
            "allocated_amount": razorpay_payment_entry.amount,
        },
    )
    if frappe.db.has_column("Payment Entry", "custom_razorpay_payment_id"):
        pe.custom_razorpay_payment_id = razorpay_payment_entry.razorpay_payment_id
    if frappe.db.has_column("Payment Entry", "custom_razorpay_order_id"):
        pe.custom_razorpay_order_id = razorpay_payment_entry.razorpay_order_id

    pe.flags.ignore_permissions = True
    pe.flags.ignore_validate = True
    pe.insert()
    pe.submit()

    try:
        gateway = RazorpayGateway()
        frappe.db.set_value("Payment Entry", pe.name, "owner", gateway.system_user)
    except Exception:
        pass

    razorpay_payment_entry.db_set("payment_entry", pe.name)
    razorpay_payment_entry.db_set("status", "COMPLETED")
    frappe.db.commit()


# ─── Internal utilities ───────────────────────────────────────────────────────

def _get_doctype(doc_name):
    for dt in ("Sales Order", "Sales Invoice", "Quotation"):
        if frappe.db.exists(dt, doc_name):
            return dt
    frappe.throw(
        _("Document {0} not found as Sales Order, Sales Invoice, or Quotation").format(doc_name)
    )


def _ensure_razorpay_payment_entry(rz_order_id, order_doc, amount):
    if frappe.db.exists("Razorpay Payment Entry", {"razorpay_order_id": rz_order_id}):
        return
    rpe = frappe.new_doc("Razorpay Payment Entry")
    rpe.name = frappe.generate_hash(length=10)
    rpe.customer = getattr(order_doc, "customer", None)
    rpe.razorpay_order_id = rz_order_id
    rpe.amount = float(amount) / 100  # paise → rupees for Frappe Currency field
    rpe.currency = "INR"
    rpe.status = "INITIATED"
    rpe.payment_method = "razorpay"
    rpe.insert(ignore_permissions=True)
    frappe.db.commit()
