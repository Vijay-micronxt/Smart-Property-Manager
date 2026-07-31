"""Task 2 -- follow-up reminders to the sales user who owns the Lead.

This is the ERPNext ``Lead`` DocType, not Frappe CRM's ``CRM Lead``. The logic
mirrors what was running against CRM Lead, but the schedule now lives in a
custom field on Lead and every send is recorded in Property Notification Log.

Reminders stop the moment the lead is closed: a status in the configured stop
list, the Disabled flag, a Customer already created from the lead, or simply an
empty follow-up date.
"""

import frappe
from frappe.utils import add_days, cint, date_diff, get_url_to_form, getdate, now_datetime, today

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)
from property_core.property_core.notifications import recipients as rc
from property_core.property_core.notifications.dispatcher import describe, notify

EVENT = "Lead Follow Up"


def run_daily_lead_follow_ups():
    settings = get_settings()
    if not settings or not settings.enabled or not settings.enable_lead_follow_up_reminders:
        return

    run_date = getdate(today())
    stop_statuses = settings.get_lead_stop_statuses()

    leads = frappe.get_all(
        "Lead",
        filters={
            "custom_next_follow_up_date": ["is", "set"],
            "custom_disable_follow_up_reminders": 0,
            "disabled": 0,
            "status": ["not in", stop_statuses] if stop_statuses else ["!=", ""],
        },
        fields=["name", "custom_next_follow_up_date", "status"],
        limit=5000,
    )

    for row in leads:
        try:
            _process_lead(row, run_date, settings)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Lead Follow-Up Reminder Error: {row.name}")

    frappe.db.commit()


def _process_lead(row, run_date, settings):
    if is_closed(row.name):
        return

    follow_up_date = getdate(row.custom_next_follow_up_date)
    kind = _occurrence_kind(follow_up_date, run_date, settings)
    if not kind:
        return

    lead = frappe.get_doc("Lead", row.name)
    recipient = rc.for_lead_owner(lead)
    if not recipient:
        frappe.log_error(
            f"Lead {lead.name} has no active follow-up owner, lead owner or assignee.",
            "Lead Follow-Up Reminder - No Recipient",
        )
        return

    days_overdue = max(date_diff(run_date, follow_up_date), 0)

    logs = notify(
        event=EVENT,
        doc=lead,
        channel=settings.lead_follow_up_channel or "Both",
        recipient=recipient,
        rule_label=kind,
        dedupe_key=f"lead-followup::{lead.name}::{follow_up_date}::{kind}::{run_date}",
        context={
            "follow_up_date": follow_up_date,
            "days_overdue": days_overdue,
            "lead_link": get_url_to_form("Lead", lead.name),
        },
    )

    if logs:
        _stamp(lead.name)


def _occurrence_kind(follow_up_date, run_date, settings):
    """'Advance', 'Due' or 'Overdue' when a reminder is owed today, else None."""
    if run_date == follow_up_date:
        return "Due"

    advance_days = cint(settings.lead_advance_reminder_days)
    if advance_days and run_date == getdate(add_days(follow_up_date, -advance_days)):
        return "Advance"

    if not settings.lead_repeat_overdue:
        return None

    elapsed = date_diff(run_date, follow_up_date)
    if elapsed <= 0:
        return None

    every = cint(settings.lead_repeat_every_days) or 1
    if elapsed % every:
        return None

    return "Overdue"


def is_closed(lead_name):
    """A lead that already produced a Customer is converted even if somebody
    forgot to move its status."""
    return bool(frappe.db.exists("Customer", {"lead_name": lead_name}))


def _stamp(lead_name):
    count = cint(frappe.db.get_value("Lead", lead_name, "custom_follow_up_reminder_count"))
    frappe.db.set_value(
        "Lead",
        lead_name,
        {
            "custom_last_reminder_sent_on": now_datetime(),
            "custom_follow_up_reminder_count": count + 1,
        },
        update_modified=False,
    )


def on_lead_update(doc, method=None):
    """Closing a lead clears its schedule, so nothing is left armed."""
    settings = get_settings()
    if not settings:
        return

    stop_statuses = settings.get_lead_stop_statuses()
    if doc.status in stop_statuses or doc.get("disabled"):
        if doc.get("custom_next_follow_up_date"):
            doc.db_set("custom_next_follow_up_date", None, update_modified=False)


@frappe.whitelist()
def send_follow_up_now(lead_name, channel=None):
    """Manual 'Send Follow-Up Reminder' from the Lead form."""
    from frappe.utils import now

    frappe.has_permission("Lead", "read", doc=lead_name, throw=True)

    settings = get_settings()
    if not settings or not settings.enabled:
        frappe.throw(frappe._("Property notifications are disabled in Property Notification Settings."))

    lead = frappe.get_doc("Lead", lead_name)
    recipient = rc.for_lead_owner(lead)
    if not recipient:
        frappe.throw(frappe._("Lead {0} has no follow-up owner, lead owner or assignee.").format(lead_name))

    follow_up_date = getdate(lead.custom_next_follow_up_date or today())
    logs = notify(
        event=EVENT,
        doc=lead,
        channel=channel or settings.lead_follow_up_channel or "Both",
        recipient=recipient,
        rule_label="Manual",
        dedupe_key=f"lead-followup::{lead_name}::manual::{now()}",
        context={
            "follow_up_date": follow_up_date,
            "days_overdue": max(date_diff(getdate(today()), follow_up_date), 0),
            "lead_link": get_url_to_form("Lead", lead_name),
        },
    )
    return {"results": describe(logs)}
