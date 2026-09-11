"""Drop the DocType Link rows that property.json and property_unit.json used to
declare.

Two problems with them. The Opportunity row pointed at `property`, a column the
rename patch moved to `custom_property`, so opening a Property blew up with
"Unknown column 'tabOpportunity.property'" the moment Connections tried to
count. And every one of them duplicated a row that property_dashboard.py /
property_unit_dashboard.py already supply, so Connections listed the same
doctype twice.

The dashboard files are the single source now. Only the rows this app shipped
are removed -- matched on doctype, fieldname and group together, so a
Connection someone added by hand survives.
"""

import frappe

STALE_LINKS = [
    ("Property", "Property Unit", "property", "Units"),
    ("Property", "Opportunity", "property", "CRM"),
    ("Property Unit", "Property Booking", "property_unit", "Transactions"),
    ("Property Unit", "Property Allocation", "property_unit", "Transactions"),
]


def execute():
    touched = set()

    for parent, link_doctype, link_fieldname, group in STALE_LINKS:
        rows = frappe.get_all(
            "DocType Link",
            filters={
                "parent": parent,
                "parenttype": "DocType",
                "link_doctype": link_doctype,
                "link_fieldname": link_fieldname,
                "group": group,
            },
            pluck="name",
        )
        for row in rows:
            frappe.db.delete("DocType Link", {"name": row})
            touched.add(parent)

    for doctype in touched:
        frappe.clear_cache(doctype=doctype)
