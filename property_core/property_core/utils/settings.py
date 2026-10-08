"""Property Core Settings, read with each field's own default as the fallback.

A Single stores only the values someone saved. A field added in a later
release has no row on a site that has not re-saved its settings, and
get_single_value then reads a Check as 0 -- every new behaviour would ship
switched off everywhere except fresh installs.
"""

import frappe
from frappe.utils import cint, flt

DOCTYPE = "Property Core Settings"


def get(fieldname):
    row = frappe.db.sql(
        "select value from `tabSingles` where doctype=%s and field=%s", (DOCTYPE, fieldname)
    )
    value = row[0][0] if row else None
    df = frappe.get_meta(DOCTYPE).get_field(fieldname)
    if value is None and df:
        value = df.default
    if not df:
        return value
    if df.fieldtype in ("Check", "Int"):
        return cint(value)
    if df.fieldtype in ("Float", "Currency", "Percent"):
        return flt(value)
    return value
