"""Opportunity.property / property_unit -> custom_property / custom_property_unit.

Frappe's mapper copies same-named fields, so Lead -> Opportunity only carries
the property interest across if both sides spell the fieldname the same way.
Lead already uses the custom_ prefix (which is also the convention for fields
added to core DocTypes), so Opportunity moves to match.

The column is renamed in place to keep existing values; the stale Custom Field
row is dropped and recreated under the new name by the after_migrate hook.
"""

import frappe

RENAMES = {
    "property": "custom_property",
    "property_unit": "custom_property_unit",
    "property_link_section": "custom_property_link_section",
}


def execute():
    if not frappe.db.table_exists("Opportunity"):
        return

    columns = set(frappe.db.get_table_columns("Opportunity"))

    for old, new in RENAMES.items():
        if old in columns and new not in columns:
            frappe.db.sql_ddl(
                f"ALTER TABLE `tabOpportunity` CHANGE COLUMN `{old}` `{new}` varchar(140)"
            )
            columns.discard(old)
            columns.add(new)

        stale = frappe.db.get_value("Custom Field", {"dt": "Opportunity", "fieldname": old})
        if stale:
            frappe.delete_doc("Custom Field", stale, force=True, ignore_missing=True)

    frappe.clear_cache(doctype="Opportunity")
