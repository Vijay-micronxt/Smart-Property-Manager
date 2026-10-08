"""Store the default of every Property Core Settings field that has none saved.

A Single keeps only what someone saved. Fields added later have no row, so
the desk form and REST read them as empty -- a Check that defaults to on shows
unchecked, and the next save of the settings writes 0 and switches it off.
"""

import frappe

DOCTYPE = "Property Core Settings"


def execute():
    frappe.reload_doc("property_core", "doctype", "property_core_settings")
    stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype=%s", DOCTYPE))
    for df in frappe.get_meta(DOCTYPE).fields:
        if df.default is None or df.fieldname in stored or df.fieldtype in ("Section Break", "Column Break", "Tab Break"):
            continue
        frappe.db.set_single_value(DOCTYPE, df.fieldname, df.default)
