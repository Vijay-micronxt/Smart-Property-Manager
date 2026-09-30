"""
Custom fields linking property_core's Property Unit to property_operations'
recurring maintenance billing. Owned by property_operations (not property_core)
-- these fields only matter when this optional app is installed, following the
same one-directional dependency already established for Issue.work_order.
"""

PROPERTY_UNIT_FIELDS = [
    {
        "fieldname": "maintenance_section",
        "fieldtype": "Section Break",
        "label": "Recurring Maintenance",
        "insert_after": "hsn_sac_code",
        "collapsible": 1,
    },
    {
        "fieldname": "maintenance_plan_template",
        "fieldtype": "Link",
        "label": "Maintenance Plan Template",
        "options": "Maintenance Plan Template",
        "insert_after": "maintenance_section",
        "description": "Optional. Drives auto-generated monthly maintenance invoices for this unit.",
    },
    {
        "fieldname": "maintenance_start_date",
        "fieldtype": "Date",
        "label": "Maintenance Start Date",
        "insert_after": "maintenance_plan_template",
        "depends_on": "eval:doc.maintenance_plan_template",
    },
    {
        "fieldname": "pause_maintenance",
        "fieldtype": "Check",
        "label": "Pause Maintenance Billing",
        "insert_after": "maintenance_start_date",
        "depends_on": "eval:doc.maintenance_plan_template",
    },
    {
        "fieldname": "maintenance_billing_history",
        "fieldtype": "HTML",
        "label": "Maintenance Billing History",
        "insert_after": "pause_maintenance",
        "depends_on": "eval:doc.maintenance_plan_template",
        "description": "Live list of auto-generated maintenance invoices for this unit -- period, amount, paid, outstanding, status. Not stored data; always reflects the actual Sales Invoices.",
    },
]


SETTINGS_FIELDS = [
    {
        "fieldname": "maintenance_item_code",
        "fieldtype": "Link",
        "label": "Maintenance Item Code",
        "options": "Item",
        "insert_after": "rent_item_code",
        "reqd": 1,
        "description": "ERPNext Item used when auto-generating recurring maintenance Sales Invoices (e.g. 'Maintenance Charge'). Mandatory -- acts as the default whenever a Maintenance Plan Template row/repeat cycle doesn't specify its own Item.",
    },
    {
        "fieldname": "maintenance_task_lead_days",
        "fieldtype": "Int",
        "label": "Open Maintenance Task Days Before",
        "insert_after": "maintenance_item_code",
        "default": "3",
        "description": "A Property Maintenance Task is opened this many days before each maintenance date on a unit's plan.",
    },
    {
        "fieldname": "maintenance_task_assignee",
        "fieldtype": "Link",
        "label": "Assign Maintenance Tasks To",
        "options": "User",
        "insert_after": "maintenance_task_lead_days",
        "description": "Optional. New maintenance tasks are assigned to this person (their desk ToDo).",
    },
    {
        "fieldname": "maintenance_proof_required",
        "fieldtype": "Check",
        "label": "Require Proof to Complete Maintenance",
        "insert_after": "maintenance_task_assignee",
        "default": "1",
        "description": "A maintenance task cannot be marked Completed until at least one photo or file is attached.",
    },
]


SALES_INVOICE_FIELDS = [
    {
        "fieldname": "property_unit",
        "fieldtype": "Link",
        "label": "Property Unit",
        "options": "Property Unit",
        "insert_after": "customer",
        # Classifies the invoice for the reminder scope; it touches no
        # accounting figure, and the field's whole purpose is to be fixable on
        # an invoice that was already submitted without it.
        "allow_on_submit": 1,
        "description": "Set by the maintenance, rent and instalment billing runs. Set it by hand on a manually raised invoice so payment reminders can find it.",
    },
    {
        "fieldname": "maintenance_period",
        "fieldtype": "Data",
        "label": "Maintenance Period",
        "insert_after": "property_unit",
        "read_only": 1,
        "description": "e.g. '2026-08' for a monthly charge, or a fixed date for a one-off charge -- used to prevent double-billing the same period",
    },
]


def sync_property_unit_link_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields({"Property Unit": PROPERTY_UNIT_FIELDS}, ignore_validate=True, update=True)
    create_custom_fields({"Property Core Settings": SETTINGS_FIELDS}, ignore_validate=True, update=True)
    _seed_settings_defaults()
    create_custom_fields({"Sales Invoice": SALES_INVOICE_FIELDS}, ignore_validate=True, update=True)


def _seed_settings_defaults():
    """A Single never stores a new field's default -- reading it gives 0 --
    so a freshly added setting would silently start switched off. Write the
    default once, only where the site has no value at all."""
    import frappe

    for field in SETTINGS_FIELDS:
        if field.get("default") in (None, ""):
            continue
        stored = frappe.db.sql(
            "select 1 from `tabSingles` where doctype=%s and field=%s",
            ("Property Core Settings", field["fieldname"]),
        )
        if not stored:
            frappe.db.set_single_value("Property Core Settings", field["fieldname"], field["default"])


def delete_property_unit_link_fields():
    """Runs on uninstall so Property Unit / Property Core Settings / Sales
    Invoice (all owned by property_core/ERPNext, not this app) revert cleanly
    -- in particular Property Core Settings.maintenance_item_code is mandatory,
    so leaving it behind after uninstall would permanently block saving that
    Single doctype for a field that no longer means anything."""
    import frappe

    frappe.db.delete(
        "Custom Field",
        {"dt": "Property Unit", "fieldname": ["in", [f["fieldname"] for f in PROPERTY_UNIT_FIELDS]]},
    )
    frappe.db.delete(
        "Custom Field",
        {"dt": "Property Core Settings", "fieldname": ["in", [f["fieldname"] for f in SETTINGS_FIELDS]]},
    )
    frappe.db.delete(
        "Custom Field",
        {"dt": "Sales Invoice", "fieldname": ["in", [f["fieldname"] for f in SALES_INVOICE_FIELDS]]},
    )
