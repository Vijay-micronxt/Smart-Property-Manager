import json
from urllib.parse import urlencode, urlparse, parse_qs

import frappe
import requests
from frappe import _

MSWIPE_ATTEMPT_BY_TRANSID_PREFIX = "mswipe_ecom_attempt:"
MSWIPE_RETURN_URL_CACHE_PREFIX = "mswipe_ecom_return_url:"


def _load_mswipe_settings():
    """Load Mswipe Settings handling both singleton and list-doctype variants.

    The doctype is defined as is_single=1 but on some installs bench migrate
    hasn't run yet, so the record lives in tabMswipe Settings with an auto-name
    rather than in tabSingles. Try singleton first; fall back to the first row.
    """
    if not frappe.db.exists("DocType", "Mswipe Settings"):
        frappe.throw(
            _("Mswipe Settings doctype not found. "
              "Run `bench migrate` on the server, then fill in credentials at /app/mswipe-settings.")
        )

    # Try singleton path (correct setup after bench migrate)
    try:
        s = frappe.get_single("Mswipe Settings")
        if s.cust_code or s.user_id:
            return s
    except Exception:
        pass

    # Fallback: doctype stored as a regular list record (bench migrate pending)
    name = frappe.db.get_value("Mswipe Settings", {}, "name")
    if name:
        try:
            return frappe.get_doc("Mswipe Settings", name)
        except Exception:
            pass

    frappe.throw(
        _("Mswipe Settings could not be loaded. "
          "Please open /app/mswipe-settings, fill in credentials, and Save.")
    )


class MswipeGateway:
    def __init__(self):
        settings = _load_mswipe_settings()
        missing = []
        self.base_url = settings.base_url
        self.cust_code = settings.cust_code
        self.user_id = settings.user_id
        self.client_id = settings.client_id
        self.password = settings.get_password("password") if settings.password else None
        self.system_user = settings.system_user

        for field in ("base_url", "cust_code", "user_id", "client_id", "password"):
            if not getattr(self, field):
                missing.append(field)
        if missing:
            frappe.throw(
                _("Mswipe Settings missing required fields: {0}").format(", ".join(missing))
            )

    def _get_session_token(self):
        cached = frappe.cache().get_value("mswipe_pbl_token")
        if cached:
            return cached

        url = f"{self.base_url}/CreatePBLAuthToken"
        payload = {
            "userId": self.user_id,
            "clientId": self.client_id,
            "password": self.password,
            "applId": "api",
            "channelId": "pbl",
        }
        data = self._make_request(url, payload)
        if str(data.get("status", "")).lower() != "true":
            frappe.throw(
                _("Mswipe auth failed: {0}").format(data.get("message", "Unknown error"))
            )

        token = data.get("sessionToken") or data.get("token") or data.get("data", {}).get("sessionToken")
        if not token:
            frappe.throw(_("Mswipe auth response did not contain a session token"))

        frappe.cache().set_value("mswipe_pbl_token", token, expires_in_sec=72000)
        return token

    def initiate_transaction(self, order_id, amount, mobileno, email, callback_url=None, return_url=None):
        session_token = self._get_session_token()

        if not callback_url:
            callback_url = frappe.utils.get_url(
                "/api/method/property_core.property_core.api.ecommerce.mswipe_webhooks.handle_mswipe_callback"
            )

        payload = {
            "amount": f"{float(amount):.2f}",
            "mobileno": mobileno,
            "custcode": self.cust_code,
            "user_id": self.user_id,
            "sessiontoken": session_token,
            "versionno": "VER4.0.0",
            "imeino": "",
            "email_id": email or "",
            "invoice_id": order_id,
            "request_id": frappe.generate_hash(length=20),
            "device_id": "",
            "addlnote1": "",
            "addlnote2": "",
            "addlnote3": "",
            "addlnote4": "",
            "addlnote5": "",
            "addlnote6": "",
            "addlnote7": "",
            "addlnote8": "",
            "addlnote9": "",
            "addlnote10": "",
            "LinkValidity": "",
            "paymentreason": "",
            "redirect_url": callback_url,
            "IsSendSMS": False,
            "ConvAllow": "false",
            "ApplicationId": "api",
            "ChannelId": "pbl",
            "ClientId": self.client_id,
        }

        data = self._make_request(f"{self.base_url}/MswipePayment", payload)

        if str(data.get("status", "")).lower() != "true":
            frappe.throw(
                _("Mswipe payment initiation failed: {0}").format(data.get("message", str(data)))
            )

        smslink = data.get("smslink") or data.get("shortUrl") or data.get("link")
        if not smslink:
            frappe.throw(_("Mswipe response missing payment link"))

        payment_url = smslink
        txn_id = data.get("txnId") or data.get("txn_id") or ""
        trans_id = self._extract_trans_id(smslink) or data.get("transId") or data.get("trans_id") or ""
        mswipe_order_id = data.get("orderId") or order_id

        self._log_transaction(
            order_id=order_id,
            mswipe_order_id=mswipe_order_id,
            mswipe_txn_id=txn_id,
            mswipe_trans_id=trans_id,
            return_url=return_url or "",
            amount=amount,
            status="INITIATED",
            response=data,
        )

        return {
            "payment_url": payment_url,
            "txn_id": txn_id,
            "trans_id": trans_id,
            "order_id": order_id,
        }

    def check_transaction_status(self, trans_id):
        url = f"{self.base_url}/getPBLTransactionDetails"
        data = self._make_request(url, {"id": trans_id})
        rows = data.get("Data") or []
        return rows[0] if rows else {}

    def _make_request(self, url, payload):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            err_detail = ""
            if hasattr(e, "response") and e.response is not None:
                try:
                    err_detail = e.response.json()
                except Exception:
                    err_detail = e.response.text
            frappe.log_error(title="Mswipe Request Error", message=str(err_detail or e))
            frappe.throw(_("Mswipe connection error: {0}").format(str(e)))

    def _log_transaction(self, order_id, mswipe_order_id, mswipe_txn_id, mswipe_trans_id,
                          return_url, amount, status, response):
        existing_name = frappe.db.get_value(
            "Mswipe Payment Entry", {"mswipe_order_id": order_id}, "name"
        )
        if existing_name:
            entry = frappe.get_doc("Mswipe Payment Entry", existing_name)
        else:
            entry = frappe.new_doc("Mswipe Payment Entry")
            entry.name = frappe.generate_hash(length=10)
            entry.mswipe_order_id = order_id

        entry.mswipe_txn_id = mswipe_txn_id or entry.mswipe_txn_id
        entry.mswipe_trans_id = mswipe_trans_id or entry.mswipe_trans_id
        entry.return_url = return_url or entry.return_url
        entry.amount = float(amount)
        entry.currency = "INR"
        entry.status = status
        entry.payment_method = "mswipe"
        entry.mswipe_response = json.dumps(response)

        try:
            if existing_name:
                entry.save(ignore_permissions=True)
            else:
                entry.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            frappe.log_error(title="Mswipe _log_transaction error", message=frappe.get_traceback())
            raise

    @staticmethod
    def _extract_trans_id(url_string):
        try:
            parsed = urlparse(url_string)
            params = parse_qs(parsed.query)
            return (params.get("TransID") or params.get("transID") or [""])[0]
        except Exception:
            return ""


# ─── Whitelisted endpoint ─────────────────────────────────────────────────────

@frappe.whitelist()
def order_payment(order_id, amount, mobileno=None, email=None,
                  store_id=None, owner_id=None, return_url=None):
    try:
        gateway = MswipeGateway()
        order_doc = frappe.get_doc(_get_doctype(order_id), order_id)

        outstanding = getattr(order_doc, "outstanding_amount", None)
        grand_total = getattr(order_doc, "grand_total", None)
        effective_amount = float(amount or outstanding or grand_total or 0)

        if effective_amount <= 0:
            frappe.throw(_("Invalid payment amount"))
        max_due = float(outstanding or grand_total or 0)
        if max_due > 0 and effective_amount > max_due:
            frappe.throw(
                _("Amount {0} exceeds outstanding {1}").format(effective_amount, max_due)
            )

        mobileno = mobileno or getattr(order_doc, "contact_mobile", None)
        email = email or getattr(order_doc, "contact_email", None)
        if not mobileno:
            frappe.throw(_("Mobile number is required for Mswipe payment"))

        result = gateway.initiate_transaction(
            order_id=order_id,
            amount=effective_amount,
            mobileno=mobileno,
            email=email,
            return_url=return_url,
        )

        frappe.cache().set_value(
            MSWIPE_ATTEMPT_BY_TRANSID_PREFIX + result["trans_id"],
            {"order_id": order_id},
            expires_in_sec=3600,
        )
        if return_url:
            frappe.cache().set_value(
                MSWIPE_RETURN_URL_CACHE_PREFIX + order_id,
                return_url,
                expires_in_sec=3600,
            )

        return {
            "status": 200,
            "data": {
                "order": {
                    "order_id": order_id,
                    "amount": effective_amount,
                    "payment_url": result["payment_url"],
                    "txn_id": result["txn_id"],
                    "trans_id": result["trans_id"],
                }
            },
        }
    except Exception as e:
        frappe.log_error(title="Mswipe order_payment error", message=frappe.get_traceback())
        return {"status": 400, "error": str(e)}


# ─── Shared payment entry creator (non-whitelisted) ──────────────────────────

def create_payment_entry_from_mswipe(mswipe_payment_entry):
    si_name = mswipe_payment_entry.sales_invoice
    if not si_name:
        frappe.throw(_("Mswipe Payment Entry has no linked Sales Invoice"))

    si = frappe.get_doc("Sales Invoice", si_name)
    company = si.company

    mop_account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": "Mswipe", "company": company},
        "default_account",
    )
    if not mop_account:
        frappe.throw(
            _("Configure default account for 'Mswipe' Mode of Payment for company {0}").format(company)
        )

    paid_from = frappe.get_cached_value("Company", company, "default_receivable_account")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = si.customer
    pe.company = company
    pe.mode_of_payment = "Mswipe"
    pe.paid_from = paid_from
    pe.paid_to = mop_account
    pe.paid_amount = mswipe_payment_entry.amount
    pe.received_amount = mswipe_payment_entry.amount
    pe.reference_no = mswipe_payment_entry.mswipe_txn_id or mswipe_payment_entry.mswipe_order_id
    pe.reference_date = frappe.utils.today()
    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": si_name,
            "allocated_amount": mswipe_payment_entry.amount,
        },
    )
    if frappe.db.has_column("Payment Entry", "custom_mswipe_txn_id"):
        pe.custom_mswipe_txn_id = mswipe_payment_entry.mswipe_txn_id
    if frappe.db.has_column("Payment Entry", "custom_mswipe_order_id"):
        pe.custom_mswipe_order_id = mswipe_payment_entry.mswipe_order_id

    pe.flags.ignore_permissions = True
    pe.flags.ignore_validate = True
    pe.insert()
    pe.submit()

    mswipe_payment_entry.db_set("payment_entry", pe.name)
    mswipe_payment_entry.db_set("status", "COMPLETED")


# ─── Internal utilities ───────────────────────────────────────────────────────

def _get_doctype(doc_name):
    for dt in ("Sales Order", "Sales Invoice", "Quotation"):
        if frappe.db.exists(dt, doc_name):
            return dt
    frappe.throw(
        _("Document {0} not found as Sales Order, Sales Invoice, or Quotation").format(doc_name)
    )
