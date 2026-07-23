"""
Custom field linking ERPNext's Issue (property_core's single customer-facing
ticket doctype) to property_operations' Work Order. Owned by property_operations,
not property_core, since it only matters when this optional app is installed --
property_core's own raise_issue() API works fine without it.
"""

ISSUE_FIELDS = [
    {
        "fieldname": "work_order",
        "fieldtype": "Link",
        "label": "Work Order",
        "options": "Work Order",
        "insert_after": "property_unit",
        "read_only": 1,
        "description": "Set automatically once a Work Order is created to resolve this Issue",
    },
]


def sync_issue_link_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields({"Issue": ISSUE_FIELDS}, ignore_validate=True, update=True)
