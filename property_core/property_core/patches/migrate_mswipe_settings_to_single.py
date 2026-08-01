"""
One-time patch: convert Mswipe Settings from a list record to a proper singleton.

Background
----------
Mswipe Settings has is_single=1 in the doctype JSON, but on the live site the
record was created as a regular list document (name = auto-generated hash) before
bench migrate properly set up the singleton structure in tabSingles.

This patch copies every field value from the first row of tabMswipe Settings into
tabSingles so that frappe.get_single("Mswipe Settings") works correctly and the
settings page opens at /app/mswipe-settings (no record name in the URL), matching
the behaviour of Razorpay Settings and Paytm Settings.

Run via:
    bench --site <site> run-patch \
        property_core.property_core.patches.migrate_mswipe_settings_to_single
"""

import frappe


def execute():
    if not frappe.db.table_exists("Mswipe Settings"):
        return  # doctype not installed; nothing to migrate

    # Fetch the first list record (if any)
    rows = frappe.db.sql(
        "SELECT name FROM `tabMswipe Settings` ORDER BY creation LIMIT 1",
        as_dict=True,
    )
    if not rows:
        return  # already empty or already migrated

    record_name = rows[0]["name"]

    # Skip if it looks like it's already the singleton record
    if record_name == "Mswipe Settings":
        return

    row = frappe.db.sql(
        "SELECT * FROM `tabMswipe Settings` WHERE name = %s",
        record_name,
        as_dict=True,
    )
    if not row:
        return

    fields = row[0]

    # Write each field into tabSingles (the singleton store)
    skip = {"name", "creation", "modified", "modified_by", "owner", "docstatus",
             "idx", "parent", "parentfield", "parenttype"}
    for fieldname, value in fields.items():
        if fieldname in skip or value is None or value == "":
            continue
        frappe.db.sql(
            """INSERT INTO `tabSingles` (doctype, field, value)
               VALUES (%s, %s, %s)
               ON DUPLICATE KEY UPDATE value = VALUES(value)""",
            ("Mswipe Settings", fieldname, value),
        )

    frappe.db.commit()
    frappe.logger().info(
        f"migrate_mswipe_settings_to_single: migrated record '{record_name}' to tabSingles"
    )
