"""Store the defaults of the push fields on Property Notification Settings.

Same trap as property_core_settings_defaults: a Single keeps only what was
saved, so the new "Enable Push Notifications" Check reads as off on every site
that already had the settings, and pushes never start.

Only the push fields are touched: any other field that was never saved reads
as off on that site today, and quietly switching it on (invoice sends,
WhatsApp, ...) is not this patch's business.
"""

import frappe

DOCTYPE = "Property Notification Settings"
FIELDS = ("enable_push_notifications", "push_daily_digest", "push_follow_up_before_minutes")


def execute():
    frappe.reload_doc("property_core", "doctype", "property_notification_settings")
    stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype=%s", DOCTYPE))
    meta = frappe.get_meta(DOCTYPE)
    for fieldname in FIELDS:
        df = meta.get_field(fieldname)
        if df and df.default is not None and fieldname not in stored:
            frappe.db.set_single_value(DOCTYPE, fieldname, df.default)
