"""
Field registry for the customer portal.

Every portal endpoint reads its field list from here instead of hardcoding one,
so adding a field to a payload later is a one-line edit -- and any custom field
added on a site (``custom_*``) is picked up automatically, without a code change.

Three layers, applied in order:

1. ``REGISTRY``          -- the app's own fields (this file).
2. ``AUTO_CUSTOM``       -- doctypes whose ``custom_*`` fields are auto-included.
3. ``portal_extra_fields`` hook -- per-site additions, e.g. in a site app's hooks.py::

       portal_extra_fields = {"Property Unit": ["custom_khata_number"]}

Fields that do not exist on the site are dropped rather than raising, so a
renamed or removed field degrades to a missing key instead of a 500.
"""

import frappe

# Fieldtypes that hold no value worth sending to a portal client.
_LAYOUT_FIELDTYPES = {
    "Section Break", "Column Break", "Tab Break", "HTML", "Button",
    "Fold", "Heading", "Table", "Table MultiSelect", "Image",
}

REGISTRY = {
    "Property": [
        "name", "property_name", "property_type", "status", "project",
        "launch_date", "total_area", "address",
        "layout_image", "layout_world_width", "layout_world_height",
    ],
    "Property Unit": [
        "name", "property", "project", "unit_number", "unit_type",
        "availability_status", "area", "facing", "floor", "base_price",
        "item_code", "customer",
    ],
    "Property Unit Layout": [
        "name", "unit_number", "unit_type", "availability_status", "area", "base_price",
        "layout_shape", "layout_x", "layout_y", "layout_w", "layout_h",
        "layout_rotation", "layout_points", "customer",
    ],
    "Property Booking": [
        "name", "customer", "property_unit", "unit_property", "project",
        "unit_type", "unit_area", "unit_base_price", "booking_date",
        "booking_status", "booking_amount", "sales_person", "notes", "docstatus",
    ],
    "Payment Plan": [
        "name", "booking", "milestone", "due_date", "amount", "invoice",
        "payment_status", "late_fee_applied", "late_fee_amount",
    ],
    "Property Allocation": [
        "name", "property_unit", "project", "allocation_type", "status",
        "start_date", "end_date", "rent_amount", "billing_frequency",
        "billing_day", "next_billing_date", "booking", "agreement",
    ],
    "Property Agreement": [
        "name", "property_unit", "project", "agreement_type", "agreement_status",
        "start_date", "end_date", "signed_date", "security_deposit_amount",
        "security_deposit_received", "document_attachment",
    ],
    "Sales Invoice": [
        "name", "posting_date", "due_date", "grand_total", "outstanding_amount",
        "status", "currency", "remarks", "property_unit", "maintenance_period",
    ],
    "Sales Invoice Item": [
        "item_code", "item_name", "description", "qty", "uom", "rate", "amount",
    ],
    "Payment Entry": [
        "name", "posting_date", "mode_of_payment", "paid_amount",
        "reference_no", "reference_date", "remarks",
    ],
    "Utility Bill": [
        "name", "property_unit", "status", "billing_period_start",
        "billing_period_end", "previous_reading", "current_reading",
        "units_consumed", "rate_per_unit", "amount", "invoice",
    ],
    "Utility Meter": ["name", "meter_number", "utility_type", "unit_of_measure"],
    "Rent Invoice Log": [
        "name", "allocation", "period_label", "period_start", "period_end",
        "invoice", "status",
    ],
    "Issue": [
        "name", "subject", "description", "status", "priority",
        "opening_date", "resolution_date", "property_unit",
    ],
    "Work Order": [
        "name", "issue", "property_unit", "status", "description",
        "scheduled_date", "completed_date", "actual_cost", "notes",
    ],
    "Inspection Checklist": [
        "name", "property_unit", "inspection_type", "inspection_date",
        "status", "overall_condition",
    ],
    "Inspection Checklist Item": ["item_name", "category", "condition", "remarks"],
    "Maintenance Schedule Row": [
        "month_no", "description", "amount", "fixed_due_date", "item_code",
    ],
    "Property Document": ["document_name", "document_type", "document_file", "expiry_date", "notes"],
    "Property Amenity": ["amenity_name"],
}

# Doctypes where every custom field is exposed without touching this file.
AUTO_CUSTOM = {
    "Property",
    "Property Unit",
    "Property Booking",
    "Property Allocation",
    "Property Agreement",
    "Issue",
    "Work Order",
}

# Never exposed to a portal client, whatever the registry or a custom field says.
BLOCKLIST = {
    "password", "api_key", "api_secret", "razorpay_secret", "paytm_merchant_key",
    "mswipe_secret", "webhook_secret",
}


def _existing(doctype):
    """Fieldnames that actually exist on this site, value-bearing only."""
    meta = frappe.get_meta(doctype)
    names = {
        df.fieldname
        for df in meta.fields
        if df.fieldtype not in _LAYOUT_FIELDTYPES and df.fieldname
    }
    names.update({"name", "owner", "creation", "modified", "docstatus", "idx"})
    return names, meta


def fields_for(doctype, registry_key=None, extra=None):
    """Resolved, site-safe field list for a doctype.

    ``registry_key`` lets one doctype have more than one payload shape
    (e.g. ``Property Unit`` vs ``Property Unit Layout``).
    """
    key = registry_key or doctype
    wanted = list(REGISTRY.get(key) or [])
    wanted += list(extra or [])

    for hook in frappe.get_hooks("portal_extra_fields") or []:
        if isinstance(hook, dict):
            wanted += list(hook.get(key) or [])

    available, meta = _existing(doctype)

    if doctype in AUTO_CUSTOM:
        wanted += [
            df.fieldname
            for df in meta.fields
            if df.fieldname
            and df.fieldname.startswith("custom_")
            and df.fieldtype not in _LAYOUT_FIELDTYPES
        ]

    seen, out = set(), []
    for fieldname in wanted:
        if fieldname in seen or fieldname in BLOCKLIST:
            continue
        if fieldname not in available:
            continue
        seen.add(fieldname)
        out.append(fieldname)

    if not out:
        # Nothing resolved -- an unregistered doctype, or a site where every
        # registered field is gone. Fall back to the doctype's own fields so the
        # caller gets data instead of a row of empty dicts.
        out = sorted(
            df.fieldname
            for df in meta.fields
            if df.fieldname
            and df.fieldname not in BLOCKLIST
            and df.fieldtype not in _LAYOUT_FIELDTYPES
        )
        out.insert(0, "name")

    return out
