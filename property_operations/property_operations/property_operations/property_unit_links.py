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
]


SALES_INVOICE_FIELDS = [
    {
        "fieldname": "property_unit",
        "fieldtype": "Link",
        "label": "Property Unit",
        "options": "Property Unit",
        "insert_after": "customer",
        "read_only": 1,
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
    create_custom_fields({"Sales Invoice": SALES_INVOICE_FIELDS}, ignore_validate=True, update=True)


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
