"""Document events on Lead, replacing JD's CRM Lead server scripts."""

import frappe
from frappe import _
from frappe.utils import get_url_to_form

from property_core.property_core.crm.lead_fields import apply_lead_status


def validate(doc, method=None):
    apply_lead_status(doc, method)
    set_follow_up_owner(doc)


def after_insert(doc, method=None):
    notify_duplicate(doc)


def set_follow_up_owner(doc):
    """JD's "ADD lead owner on first save" — whoever creates it owns it until
    somebody says otherwise."""
    if not doc.get("lead_owner"):
        doc.lead_owner = doc.owner or frappe.session.user
    if not doc.get("custom_follow_up_owner"):
        doc.custom_follow_up_owner = doc.lead_owner


@frappe.whitelist()
def find_duplicates(mobile_no, exclude=None):
    """Every Lead already holding this number. Used by the form as you type and
    by after_insert to warn the original owner."""
    digits = "".join(ch for ch in str(mobile_no or "") if ch.isdigit())
    if len(digits) < 10:
        return []

    tail = digits[-10:]
    filters = [
        ["Lead", "mobile_no", "like", f"%{tail}"],
    ]
    if exclude:
        filters.append(["Lead", "name", "!=", exclude])

    return frappe.get_all(
        "Lead",
        filters=filters,
        fields=["name", "lead_name", "custom_lead_status", "lead_owner", "creation"],
        order_by="creation asc",
        limit=5,
        ignore_permissions=True,
    )


def notify_duplicate(doc):
    """Port of JD's notify_duplicate_lead_attempt: tell the user who already
    owns this number that the same person came in again."""
    if not doc.get("mobile_no"):
        return

    duplicates = find_duplicates(doc.mobile_no, exclude=doc.name)
    if not duplicates:
        return

    original = duplicates[0]
    owner = original.get("lead_owner")
    if not owner or owner == frappe.session.user:
        return

    try:
        frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": owner,
                "type": "Alert",
                "document_type": "Lead",
                "document_name": original["name"],
                "subject": _("Duplicate enquiry for {0}").format(doc.mobile_no),
                "email_content": _(
                    "{0} created {1} with the same number as your lead {2} ({3})."
                ).format(
                    frappe.utils.get_fullname(frappe.session.user),
                    f'<a href="{get_url_to_form("Lead", doc.name)}">{doc.name}</a>',
                    f'<a href="{get_url_to_form("Lead", original["name"])}">{original["name"]}</a>',
                    original.get("custom_lead_status") or "",
                ),
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Duplicate Lead Notification: {doc.name}")
