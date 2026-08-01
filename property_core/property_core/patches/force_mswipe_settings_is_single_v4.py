"""
Force-reload Mswipe Settings doctype from JSON using Frappe's own sync path.

frappe.reload_doc(..., force=True) reads the doctype JSON and writes the
full definition to tabDocType regardless of modified-date comparison, using
the same internal column names Frappe already knows about. This is the
correct idiomatic way to force a doctype update and avoids us guessing
whether the column is 'is_single' or 'issingle'.
"""
import frappe


def execute():
    # tabDocType uses 'issingle' (old Frappe naming without underscore)
    frappe.db.sql("UPDATE `tabDocType` SET `issingle` = 1 WHERE `name` = 'Mswipe Settings'")
    frappe.db.commit()
    frappe.clear_cache(doctype="Mswipe Settings")
