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
    frappe.reload_doc("property_core", "doctype", "mswipe_settings", force=True)
    frappe.clear_cache(doctype="Mswipe Settings")
    frappe.db.commit()
