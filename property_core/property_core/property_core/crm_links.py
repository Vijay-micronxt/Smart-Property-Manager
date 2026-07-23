"""
Custom fields linking ERPNext's CRM/Support doctypes (Opportunity, Issue) to
property_core's own doctypes (Property, Property Unit).

Defined here and applied via an after_migrate hook (see hooks.py) — the
`custom_fields` hooks.py key alone is not read by Frappe anywhere, it has to
be pushed through create_custom_fields() explicitly (same fix already applied
for the Customer KYC fields in customer_kyc.py).
"""

OPPORTUNITY_FIELDS = [
    {
        "fieldname": "property_link_section",
        "fieldtype": "Section Break",
        "label": "Property Interest",
        "insert_after": "opportunity_type",
        "collapsible": 1,
    },
    {
        "fieldname": "property",
        "fieldtype": "Link",
        "label": "Property",
        "options": "Property",
        "insert_after": "property_link_section",
        "in_standard_filter": 1,
        "description": "Which Property this opportunity is about, if known",
    },
    {
        "fieldname": "property_unit",
        "fieldtype": "Link",
        "label": "Property Unit",
        "options": "Property Unit",
        "insert_after": "property",
        "description": "Which specific unit the prospect is interested in, if known",
    },
]

ISSUE_FIELDS = [
    {
        "fieldname": "property_unit",
        "fieldtype": "Link",
        "label": "Property Unit",
        "options": "Property Unit",
        "insert_after": "customer",
        "in_standard_filter": 1,
        "description": "Unit this query/complaint relates to, if any",
    },
]


def sync_crm_link_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields({"Opportunity": OPPORTUNITY_FIELDS}, ignore_validate=True, update=True)
    create_custom_fields({"Issue": ISSUE_FIELDS}, ignore_validate=True, update=True)
