"""Make the gateway settings doctypes actual Singles, and keep them that way.

Razorpay, Mswipe and Paytm Settings are read with frappe.get_single(), but none
of their JSONs ever carried issingle. On a site where these doctypes belong to
property_core rather than the payments app, every gateway call died on
"Razorpay Settings Razorpay Settings not found".

Four earlier patches tried to force the flag straight in tabDocType. They could
not hold: the JSON is the source of truth, so the next bench migrate synced it
back to 0 every time. The JSON now says issingle, and this patch carries any
credentials that were saved as ordinary rows into tabSingles so the flip does
not lose them.
"""

import frappe

SETTINGS = ("Razorpay Settings", "Mswipe Settings", "Paytm Settings")


def execute():
    for doctype in SETTINGS:
        if not frappe.db.exists("DocType", doctype):
            continue

        _migrate_rows_into_singles(doctype)

        if not frappe.db.get_value("DocType", doctype, "issingle"):
            frappe.db.set_value("DocType", doctype, "issingle", 1, update_modified=False)

        frappe.clear_cache(doctype=doctype)


def _migrate_rows_into_singles(doctype):
    """Copy the most recently edited row's values across, but never overwrite
    values already sitting in tabSingles."""
    if not frappe.db.table_exists(doctype):
        return

    rows = frappe.db.sql(
        f"SELECT name FROM `tab{doctype}` ORDER BY modified DESC LIMIT 1", as_dict=True
    )
    if not rows:
        return

    existing = set(
        frappe.db.sql_list("SELECT field FROM tabSingles WHERE doctype = %s", doctype)
    )

    values = frappe.db.sql(
        f"SELECT * FROM `tab{doctype}` WHERE name = %s", rows[0]["name"], as_dict=True
    )[0]

    skip = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
            "parent", "parentfield", "parenttype", "_user_tags", "_comments",
            "_assign", "_liked_by"}

    for field, value in values.items():
        if field in skip or field in existing or value in (None, ""):
            continue
        frappe.db.sql(
            "INSERT INTO tabSingles (doctype, field, value) VALUES (%s, %s, %s)",
            (doctype, field, value),
        )
