"""Click-to-call, ported off JD's `call_via_exotel` server script.

Two things were wrong with the original and are fixed here:
  * the account SID, API key and token were literals in the script body --
    they now come from Property Core Settings
  * the payload had hardcoded test numbers, so every click called the same two
    phones regardless of which lead was open
"""

import frappe
from frappe import _

EXOTEL_CONNECT_URL = "https://api.exotel.com/v1/Accounts/{sid}/Calls/connect"


def _settings():
    settings = frappe.get_cached_doc("Property Core Settings")
    if not settings.get("enable_click_to_call"):
        frappe.throw(_("Click-to-call is switched off in Property Core Settings."))
    return settings


def normalise(number):
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"91{digits}"
    return f"+{digits}"


@frappe.whitelist()
def click_to_call(to_number, reference_doctype=None, reference_name=None):
    settings = _settings()

    customer_number = normalise(to_number)
    if not customer_number:
        frappe.throw(_("The number on this record is not dialable."))

    agent_number = normalise(
        frappe.db.get_value("User", frappe.session.user, "mobile_no")
        or frappe.db.get_value("User", frappe.session.user, "phone")
    )
    if not agent_number:
        frappe.throw(_("Set your mobile number on your User profile before placing a call."))

    if (settings.get("telephony_provider") or "Exotel") != "Exotel":
        frappe.throw(_("Only Exotel is wired up for click-to-call right now."))

    sid = settings.get("exotel_account_sid")
    api_key = settings.get("exotel_api_key")
    api_token = settings.get_password("exotel_api_token", raise_exception=False)
    caller_id = settings.get("exotel_caller_id")

    if not (sid and api_key and api_token and caller_id):
        frappe.throw(_("Exotel credentials are incomplete in Property Core Settings."))

    payload = {
        # Exotel rings the agent first, then bridges the customer in.
        "From": agent_number,
        "To": customer_number,
        "CallerId": caller_id,
        "CallType": "trans",
    }

    try:
        response = frappe.make_post_request(
            EXOTEL_CONNECT_URL.format(sid=sid), data=payload, auth=(api_key, api_token)
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Click To Call Failed")
        frappe.throw(_("The call could not be placed. The telephony log has the details."))

    if reference_doctype and reference_name:
        _log_call(reference_doctype, reference_name, customer_number, agent_number)

    frappe.msgprint(_("Calling {0} — pick up your phone.").format(customer_number), alert=True)
    return response


def _log_call(reference_doctype, reference_name, customer_number, agent_number):
    try:
        frappe.get_doc(
            {
                "doctype": "Property Follow Up",
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "follow_up_type": "Call",
                "status": "Completed",
                "scheduled_on": frappe.utils.now_datetime(),
                "assigned_to": frappe.session.user,
                "notes": f"Click-to-call {agent_number} -> {customer_number}",
            }
        ).insert(ignore_permissions=True)
    except Exception:
        # A missing log must never swallow a call that actually connected.
        frappe.log_error(frappe.get_traceback(), "Click To Call - follow-up log failed")


TELEPHONY_FIELDS = [
    {
        "fieldname": "section_telephony",
        "fieldtype": "Section Break",
        "label": "Telephony",
        "insert_after": "whatsapp_enabled",
    },
    {
        "fieldname": "enable_click_to_call",
        "fieldtype": "Check",
        "label": "Enable Click To Call",
        "insert_after": "section_telephony",
        "default": "0",
    },
    {
        "fieldname": "telephony_provider",
        "fieldtype": "Select",
        "label": "Provider",
        "options": "Exotel",
        "default": "Exotel",
        "depends_on": "enable_click_to_call",
        "insert_after": "enable_click_to_call",
    },
    {
        "fieldname": "exotel_account_sid",
        "fieldtype": "Data",
        "label": "Exotel Account SID",
        "depends_on": "enable_click_to_call",
        "insert_after": "telephony_provider",
    },
    {
        "fieldname": "exotel_caller_id",
        "fieldtype": "Data",
        "label": "Exotel Caller ID",
        "depends_on": "enable_click_to_call",
        "insert_after": "exotel_account_sid",
    },
    {
        "fieldname": "column_break_telephony",
        "fieldtype": "Column Break",
        "insert_after": "exotel_caller_id",
    },
    {
        "fieldname": "exotel_api_key",
        "fieldtype": "Data",
        "label": "Exotel API Key",
        "depends_on": "enable_click_to_call",
        "insert_after": "column_break_telephony",
    },
    {
        "fieldname": "exotel_api_token",
        "fieldtype": "Password",
        "label": "Exotel API Token",
        "depends_on": "enable_click_to_call",
        "insert_after": "exotel_api_key",
    },
]


def sync_telephony_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {"Property Core Settings": TELEPHONY_FIELDS}, ignore_validate=True, update=True
    )


def delete_telephony_fields():
    frappe.db.delete(
        "Custom Field",
        {
            "dt": "Property Core Settings",
            "fieldname": ["in", [f["fieldname"] for f in TELEPHONY_FIELDS]],
        },
    )
