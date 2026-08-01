"""
Force Mswipe Settings to be a proper singleton in the database.

bench migrate updates tabDocType from the JSON only when the JSON modified date
is newer than the DB record. In practice that comparison is unreliable for
doctypes that were first installed as list records. This patch does the update
unconditionally so the settings page behaves exactly like Razorpay Settings
and Paytm Settings.
"""

import frappe


def execute():
    # 1. Force is_single on the doctype metadata row
    frappe.db.sql(
        "UPDATE `tabDocType` SET is_single = 1 WHERE `name` = 'Mswipe Settings'"
    )

    # 2. Migrate any field data from the old list record into tabSingles
    if frappe.db.table_exists("Mswipe Settings"):
        rows = frappe.db.sql(
            "SELECT * FROM `tabMswipe Settings` ORDER BY creation LIMIT 1",
            as_dict=True,
        )
        if rows:
            skip = {"name", "creation", "modified", "modified_by", "owner",
                    "docstatus", "idx", "parent", "parentfield", "parenttype"}
            for fieldname, value in rows[0].items():
                if fieldname in skip or value is None or value == "":
                    continue
                frappe.db.sql(
                    """INSERT INTO `tabSingles` (doctype, field, value)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE value = VALUES(value)""",
                    ("Mswipe Settings", fieldname, value),
                )

    frappe.db.commit()

    # 3. Clear the metadata cache for this doctype so the desk router picks up is_single
    frappe.clear_cache(doctype="Mswipe Settings")
