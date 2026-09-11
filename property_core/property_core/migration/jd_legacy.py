"""What property_core now replaces on the JD site, and how to stand it down.

JD ran the whole property business on relabelled ERPNext doctypes: Sales Order
was "Booking Form", Item was "Plot", and the CRM lived in Frappe CRM's CRM
Lead. property_core now owns all of that on its own doctypes, so the site-level
customisations can go quiet.

Nothing here deletes a script. ``disable_legacy_scripts`` only flips the
``disabled`` flag, and every entry is listed with what took over, so the swap
can be checked one row at a time -- and reversed by flipping the flag back.

Usage, safe first:

    bench --site <site> execute property_core.property_core.migration.jd_legacy.report
    bench --site <site> execute property_core.property_core.migration.jd_legacy.revert_doctype_labels
    bench --site <site> execute property_core.property_core.migration.jd_legacy.disable_legacy_scripts

Each of those is a dry run. Pass apply=True to actually write:

    bench --site <site> execute property_core.property_core.migration.jd_legacy.revert_doctype_labels \
        --kwargs "{'apply': True}"
"""

import frappe

# Relabels applied through Translation rows -- this is what renamed Item to
# "Plot" and Sales Order to "Booking Form" across the whole desk.
LEGACY_TRANSLATIONS = {
    "Item": "Plot",
    "Item Code": "Plot",
    "Item Name": "Plot Name",
    "Item Group": "Plot Group",
    "Sales Order": "Booking Form",
    "CRM Deal": "Booking",
    "CRM Task": "Follow UP",
    "CRM Organization": "CRM Projects",
}

# script name -> what in property_core does the job now
SUPERSEDED_SERVER_SCRIPTS = {
    # booking, when a booking was a Sales Order
    "Booking Form - Plot Booked on Create": "Property Booking.on_submit -> availability_engine.reserve_unit",
    "Booking Form - Plot Sold on Submit": "Property Booking.on_submit -> availability_engine.reserve_unit",
    "Booking Form - Recompute Plot on Cancel": "Property Booking.on_cancel -> availability_engine.release_unit",
    "Booking Form - Recompute Plot on Delete": "Property Booking.on_cancel -> availability_engine.release_unit",
    "Booking Form - Require Rate and Area": "Property Unit.area / base_price, Property Booking.validate",
    "Booking Form - Validate Plot Project": "Property Unit.property is a mandatory link -- cannot mismatch",
    "Booking Form - Create Customer Portal User": "Property Booking.after_insert -> portal_user.ensure_portal_user",
    "Booking Form - Installment WhatsApp Reminder": "notifications.payment_reminders.run_daily_payment_reminders",
    "Booking Form - Record Maintenance Payment": "api.portal.billing",
    "Customer - Create Portal User": "portal_user.ensure_portal_user",
    # customer portal
    "Customer Portal - Get Data": "api.portal.profile / dashboard",
    "Customer Portal - Book Plot": "api.portal.bookings",
    "Customer Portal - Raise Issue": "api.portal.support",
    "Customer Portal - Maintenance Charges": "api.portal.maintenance",
    # inventory and layout
    "Plot Layout - Get Data": "Plot Layout Editor page (property_core)",
    "Plot Layout - Save": "Plot Layout Editor page (property_core)",
    "Plot - Sync Selling Price From Rate": "Property Unit.base_price",
    "Plot Maintenance - Generate Invoices & Remind": "property_operations.utils.maintenance_billing",
    # drive
    "Auto Create Drive Folders on Project": "utils.drive_folders.ensure_property_folders (on Property)",
    "Create Project Drive Subfolders": "utils.drive_folders.ensure_property_folders",
    # crm, when the CRM was Frappe CRM
    "Lead Follow-up WhatsApp Reminder": "notifications.lead_followup.run_daily_lead_follow_ups",
    "ADD lead owner on first save": "crm.lead_events.set_follow_up_owner",
    "CRM Lead Duplicate Notification": "crm.lead_events.notify_duplicate",
    "crm lead permission": "crm.lead_permissions.get_permission_query_conditions",
    "crm lead custom task api": "Property Follow Up.get_follow_up_history",
    "crm lead custom task 2nd part": "Property Follow Up.get_follow_up_history",
    "create a new task based on lead task": "Property Follow Up",
    "fetch the lead data to todo for whatsapp": "Property Follow Up.sync_todo",
    "call_via_exotel": "crm.telephony.click_to_call",
    "Call Log to CRM Lead": "crm.call_log.after_insert",
    "crm lead before insert from call log": "crm.call_log.after_insert",
    "remove old assignment with new one": "crm.call_log.keep_single_assignment",
}

SUPERSEDED_CLIENT_SCRIPTS = {
    "Dynamic data for dropdown lead source/sataus": "Lead.custom_lead_status / custom_lead_source",
    "copy status in custom ststus": "crm.lead_fields.apply_lead_status",
    "Add whatsapp icon button": "public/js/lead_crm_list.js",
    "lead exolat call function": "public/js/lead_crm_list.js",
    "mobile number button": "public/js/lead_crm_list.js",
    "show the task history in html field": "public/js/follow_up_widget.js",
    "crm lead custom task": "public/js/follow_up_widget.js",
    "notify the duplicate lead": "public/js/lead_crm.js",
    "Booking Form - Maintenance Schedule Preview": "public/js/property_unit_maintenance.js",
    "Booking Form - Plot Rate and Area": "Property Booking form",
    "Plot - Block Duplicate Sales Order": "availability_engine.assert_unit_available",
    "Plot - Layout Editor": "Plot Layout Editor page",
    "Plot - Project Plots Table Logic": "Property Unit list under Property",
    "Plot - Project Pass To Customer": "Property Booking.customer",
    "Plot - Customer Auto Project": "Property Booking",
    "Plot - Item Non Stock Default": "Property Unit is not an Item",
    "Project Drive Folder Button": "public/js/property.js (Documents button on Property)",
    "Task - Autofill Customer From Plot": "Property Follow Up",
}

# Things NOT replaced -- left alone on purpose, listed so nobody assumes.
NOT_SUPERSEDED = {
    "Sync Drive Permissions on Project Save": "Drive sharing is still Project-based; no property_core equivalent yet.",
    "Mobile no before save": "Phone normalisation on CRM Lead. Lead does not do this yet.",
    "clear the link record for crm lead delete": "CRM Lead housekeeping, irrelevant once CRM Lead is retired.",
    "Override the delivery date mandatory": "Only matters while bookings are Sales Orders.",
}


def _exists(doctype, name):
    return frappe.db.exists(doctype, name)


def report():
    """Read-only. What of the old setup is still live on this site."""
    lines = ["", "=== DocType relabels (Translation rows) ==="]
    for source, target in LEGACY_TRANSLATIONS.items():
        rows = frappe.get_all(
            "Translation", filters={"source_text": source, "translated_text": target}, pluck="name"
        )
        lines.append(f"  [{'LIVE' if rows else '  - '}] {source} -> {target}")

    lines.append("")
    lines.append("=== Server Scripts superseded by property_core ===")
    for name, replacement in SUPERSEDED_SERVER_SCRIPTS.items():
        if not _exists("Server Script", name):
            continue
        disabled = frappe.db.get_value("Server Script", name, "disabled")
        lines.append(f"  [{'off ' if disabled else 'LIVE'}] {name}\n           -> {replacement}")

    lines.append("")
    lines.append("=== Client Scripts superseded by property_core ===")
    for name, replacement in SUPERSEDED_CLIENT_SCRIPTS.items():
        if not _exists("Client Script", name):
            continue
        enabled = frappe.db.get_value("Client Script", name, "enabled")
        lines.append(f"  [{'LIVE' if enabled else 'off '}] {name}\n           -> {replacement}")

    lines.append("")
    lines.append("=== Left alone (no property_core replacement) ===")
    for name, why in NOT_SUPERSEDED.items():
        lines.append(f"  {name}\n           {why}")

    print("\n".join(lines))
    return lines


def revert_doctype_labels(apply=False):
    """Drop the Translation rows that renamed Item to Plot and Sales Order to
    Booking Form, so the desk reads as stock ERPNext again."""
    removed = []
    for source, target in LEGACY_TRANSLATIONS.items():
        for name in frappe.get_all(
            "Translation", filters={"source_text": source, "translated_text": target}, pluck="name"
        ):
            removed.append(f"{source} -> {target} ({name})")
            if apply:
                frappe.delete_doc("Translation", name, force=True, ignore_missing=True)

    if apply:
        frappe.db.commit()
        frappe.clear_cache()

    print(("REMOVED " if apply else "WOULD REMOVE ") + f"{len(removed)} translation(s)")
    for row in removed:
        print("  " + row)
    return removed


def disable_legacy_scripts(apply=False, server=True, client=True):
    """Flip `disabled` on the site scripts property_core has taken over.

    Nothing is deleted -- flip the flag back to restore the old behaviour.
    """
    touched = []

    if server:
        for name in SUPERSEDED_SERVER_SCRIPTS:
            if not _exists("Server Script", name):
                continue
            if frappe.db.get_value("Server Script", name, "disabled"):
                continue
            touched.append(f"Server Script: {name}")
            if apply:
                frappe.db.set_value("Server Script", name, "disabled", 1)

    if client:
        for name in SUPERSEDED_CLIENT_SCRIPTS:
            if not _exists("Client Script", name):
                continue
            if not frappe.db.get_value("Client Script", name, "enabled"):
                continue
            touched.append(f"Client Script: {name}")
            if apply:
                frappe.db.set_value("Client Script", name, "enabled", 0)

    if apply:
        frappe.db.commit()
        frappe.clear_cache()

    print(("DISABLED " if apply else "WOULD DISABLE ") + f"{len(touched)} script(s)")
    for row in touched:
        print("  " + row)
    return touched


def restore_legacy_scripts(apply=False):
    """Undo disable_legacy_scripts, in case a replacement turns out to be
    missing something in production."""
    touched = []

    for name in SUPERSEDED_SERVER_SCRIPTS:
        if _exists("Server Script", name) and frappe.db.get_value("Server Script", name, "disabled"):
            touched.append(f"Server Script: {name}")
            if apply:
                frappe.db.set_value("Server Script", name, "disabled", 0)

    for name in SUPERSEDED_CLIENT_SCRIPTS:
        if _exists("Client Script", name) and not frappe.db.get_value("Client Script", name, "enabled"):
            touched.append(f"Client Script: {name}")
            if apply:
                frappe.db.set_value("Client Script", name, "enabled", 1)

    if apply:
        frappe.db.commit()
        frappe.clear_cache()

    print(("RESTORED " if apply else "WOULD RESTORE ") + f"{len(touched)} script(s)")
    return touched
