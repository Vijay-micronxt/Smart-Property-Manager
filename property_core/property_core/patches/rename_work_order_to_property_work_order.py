"""Move this app's "Work Order" to "Property Work Order" and give ERPNext its
own Work Order back.

Both apps ship a doctype called "Work Order"; whichever synced last owned the
DocType row. Where this app won, ERPNext Manufacturing's Work Order was gone,
and where a site customises ERPNext's (JD: erpnext_enhancements'
override_doctype_class) every one of our inserts ran the manufacturing
controller and failed -- the operations.* work order API never worked there.

Runs before model sync. Only acts when the DocType row is ours (module
Property Operations): the table is renamed so the rows survive, references to
those rows are repointed, and the old DocType row is removed without dropping
the table. Model sync then creates "Property Work Order" over the renamed
table and recreates ERPNext's Work Order from its own JSON.
"""

import frappe

OLD, NEW = "Work Order", "Property Work Order"

# (table, doctype column, name column)
REFERENCES = [
    ("File", "attached_to_doctype", "attached_to_name"),
    ("Comment", "reference_doctype", "reference_name"),
    ("Communication", "reference_doctype", "reference_name"),
    ("Version", "ref_doctype", "docname"),
    ("ToDo", "reference_type", "reference_name"),
    ("Activity Log", "reference_doctype", "reference_name"),
    ("DocShare", "share_doctype", "share_name"),
    ("Error Log", "reference_doctype", "reference_name"),
]


def execute():
    if frappe.db.get_value("DocType", OLD, "module") != "Property Operations":
        return
    if frappe.db.table_exists(NEW):
        return

    names = frappe.db.sql_list(f"select name from `tab{OLD}`") if frappe.db.table_exists(OLD) else []
    frappe.db.sql_ddl(f"rename table `tab{OLD}` to `tab{NEW}`")

    if names:
        for table, dt_col, name_col in REFERENCES:
            if not frappe.db.table_exists(table) or not frappe.db.has_column(table, dt_col):
                continue
            frappe.db.sql(
                f"update `tab{table}` set `{dt_col}`=%s where `{dt_col}`=%s and `{name_col}` in %s",
                (NEW, OLD, tuple(names)),
            )

    # the row only -- frappe.delete_doc("DocType") would drop the table we just moved
    for child in ("DocField", "DocPerm", "DocType Link", "DocType Action", "DocType State", "Custom DocPerm"):
        if frappe.db.table_exists(child):
            frappe.db.delete(child, {"parent": OLD})
    # Custom Fields / Property Setters on "Work Order" stay: on a site that
    # customises ERPNext's Work Order they belong to that one
    frappe.db.delete("DocType", {"name": OLD})
    frappe.clear_cache()
