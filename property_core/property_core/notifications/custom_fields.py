"""Custom fields the notification engine needs on ERPNext-native DocTypes.

Applied through an after_migrate hook (see hooks.py) rather than the
``custom_fields`` key -- Frappe does not read that key on its own, the same
reason customer_kyc.py and crm_links.py push their fields explicitly.
"""

import frappe

LEAD_FIELDS = [
    {
        "fieldname": "property_follow_up_section",
        "fieldtype": "Section Break",
        "label": "Follow-Up",
        "insert_after": "status",
        "collapsible": 0,
    },
    {
        "fieldname": "custom_next_follow_up_date",
        "fieldtype": "Date",
        "label": "Next Follow-Up Date",
        "insert_after": "property_follow_up_section",
        "in_standard_filter": 1,
        "description": "Reminders go to the follow-up owner on this date. Clear it or close the lead to stop them.",
    },
    {
        "fieldname": "custom_follow_up_owner",
        "fieldtype": "Link",
        "label": "Follow-Up Owner",
        "options": "User",
        "insert_after": "custom_next_follow_up_date",
        "description": "Who gets reminded. Falls back to Lead Owner, then the assigned user.",
    },
    {
        "fieldname": "custom_follow_up_notes",
        "fieldtype": "Small Text",
        "label": "Follow-Up Notes",
        "insert_after": "custom_follow_up_owner",
    },
    {
        "fieldname": "property_follow_up_col",
        "fieldtype": "Column Break",
        "insert_after": "custom_follow_up_notes",
    },
    {
        "fieldname": "custom_disable_follow_up_reminders",
        "fieldtype": "Check",
        "label": "Disable Follow-Up Reminders",
        "insert_after": "property_follow_up_col",
        "default": "0",
    },
    {
        "fieldname": "custom_last_reminder_sent_on",
        "fieldtype": "Datetime",
        "label": "Last Reminder Sent On",
        "insert_after": "custom_disable_follow_up_reminders",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "custom_follow_up_reminder_count",
        "fieldtype": "Int",
        "label": "Reminders Sent",
        "insert_after": "custom_last_reminder_sent_on",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "property_interest_section",
        "fieldtype": "Section Break",
        "label": "Property Interest",
        "insert_after": "custom_follow_up_reminder_count",
        "collapsible": 1,
    },
    {
        "fieldname": "custom_property",
        "fieldtype": "Link",
        "label": "Property",
        "options": "Property",
        "insert_after": "property_interest_section",
        "in_standard_filter": 1,
    },
    {
        "fieldname": "custom_property_unit",
        "fieldtype": "Link",
        "label": "Property Unit",
        "options": "Property Unit",
        "insert_after": "custom_property",
    },
]

SALES_INVOICE_FIELDS = [
    {
        "fieldname": "property_notification_section",
        "fieldtype": "Section Break",
        "label": "Property Notifications",
        "insert_after": "is_return",
        "collapsible": 1,
    },
    # Property Unit is not repeated here on purpose -- Sales Invoice already
    # carries a `property_unit` field from property_unit_links.py, and that is
    # the one payment reminders read.
    {
        "fieldname": "custom_disable_payment_reminders",
        "fieldtype": "Check",
        "label": "Disable Payment Reminders",
        "insert_after": "property_notification_section",
        "default": "0",
    },
    {
        "fieldname": "custom_skip_property_notifications",
        "fieldtype": "Check",
        "label": "Do Not Send This Invoice",
        "insert_after": "custom_disable_payment_reminders",
        "default": "0",
        "description": "Skips the automatic send on submit. Manual send from the toolbar still works.",
    },
]

PAYMENT_ENTRY_FIELDS = [
    {
        "fieldname": "property_reconciliation_section",
        "fieldtype": "Section Break",
        "label": "Property Reconciliation",
        "insert_after": "references",
        "collapsible": 1,
    },
    {
        "fieldname": "custom_auto_reconciled",
        "fieldtype": "Check",
        "label": "Auto-Reconciled",
        "insert_after": "property_reconciliation_section",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "fieldname": "custom_skip_auto_reconcile",
        "fieldtype": "Check",
        "label": "Do Not Auto-Reconcile",
        "insert_after": "custom_auto_reconciled",
        "default": "0",
    },
    {
        "fieldname": "custom_skip_property_notifications",
        "fieldtype": "Check",
        "label": "Do Not Send Receipt",
        "insert_after": "custom_skip_auto_reconcile",
        "default": "0",
    },
    {
        "fieldname": "custom_reconciliation_error",
        "fieldtype": "Small Text",
        "label": "Reconciliation Note",
        "insert_after": "custom_skip_property_notifications",
        "read_only": 1,
        "no_copy": 1,
    },
]

ALL_FIELDS = {
    "Lead": LEAD_FIELDS,
    "Sales Invoice": SALES_INVOICE_FIELDS,
    "Payment Entry": PAYMENT_ENTRY_FIELDS,
}


def sync_notification_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(ALL_FIELDS, ignore_validate=True, update=True)


def delete_notification_fields():
    for doctype, fields in ALL_FIELDS.items():
        frappe.db.delete(
            "Custom Field",
            {"dt": doctype, "fieldname": ["in", [f["fieldname"] for f in fields]]},
        )
