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
    # 1. Detect the actual column name — old Frappe uses 'issingle', new uses 'is_single'
    columns = {row["Field"] for row in frappe.db.sql("SHOW COLUMNS FROM `tabDocType`", as_dict=True)}
    if "is_single" in columns:
        col = "is_single"
    elif "issingle" in columns:
        col = "issingle"
    else:
        frappe.logger().warning("force_mswipe_settings_is_single_v2: cannot find is_single column in tabDocType")
        col = None

    if col:
        frappe.db.sql(f"UPDATE `tabDocType` SET `{col}` = 1 WHERE `name` = 'Mswipe Settings'")

    # 2. Migrate field data from the old list record into tabSingles
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

    # 3. Clear the metadata cache so the desk router picks up is_single immediately
    frappe.clear_cache(doctype="Mswipe Settings")
