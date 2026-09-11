"""Task 4 -- reminders before and after the due date, until the invoice is paid.

The schedule is data, not code: every rule row in Property Notification
Settings is evaluated against each open invoice. Reminders stop on their own
because a paid invoice has no outstanding amount and therefore never enters the
candidate list.
"""

import frappe
from frappe.utils import add_days, cint, date_diff, flt, getdate, today

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)
from property_core.property_core.notifications import recipients as rc
from property_core.property_core.notifications.dispatcher import describe, notify
from property_core.property_core.notifications.invoice import linked_property_unit

EVENT = "Payment Reminder"


def run_daily_payment_reminders():
    settings = get_settings()
    if not settings or not settings.enabled or not settings.enable_payment_reminders:
        return

    rules = [r for r in (settings.payment_reminder_rules or []) if r.enabled]
    if not rules:
        return

    run_date = getdate(today())

    for invoice in _open_invoices(settings):
        try:
            _process_invoice(invoice, rules, run_date, settings)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Payment Reminder Error: {invoice.name}"
            )

    frappe.db.commit()


def _open_invoices(settings):
    """Every invoice still owing money, narrowed to the configured scope.

    Scope resolution is deliberately three bulk queries rather than a lookup per
    invoice -- a live site can carry thousands of open receivables and this runs
    daily.
    """
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "outstanding_amount": [">", 0],
            "status": ["not in", ["Paid", "Credit Note Issued", "Cancelled", "Draft", "Return"]],
            "is_return": 0,
            "due_date": ["is", "set"],
            "custom_disable_payment_reminders": 0,
        },
        fields=[
            "name", "customer", "due_date", "outstanding_amount",
            "grand_total", "currency", "company", "property_unit",
        ],
        limit=5000,
    )

    if not invoices or settings.payment_reminder_scope == "All Sales Invoices":
        return invoices

    names = [inv.name for inv in invoices]
    linked = {inv.name for inv in invoices if inv.property_unit}
    linked.update(frappe.get_all("Payment Plan", filters={"invoice": ["in", names]}, pluck="invoice"))
    linked.update(frappe.get_all("Rent Invoice Log", filters={"invoice": ["in", names]}, pluck="invoice"))

    return [inv for inv in invoices if inv.name in linked]


def _process_invoice(invoice, rules, run_date, settings):
    due_date = getdate(invoice.due_date)
    days_past_due = date_diff(run_date, due_date)

    for idx, rule in enumerate(rules):
        occurrence = _due_occurrence(rule, due_date, run_date)
        if occurrence is None:
            continue

        dedupe = f"payment-reminder::{invoice.name}::{idx}"
        if rule.repeat_after_offset:
            dedupe = f"{dedupe}::{occurrence}"

        _send(invoice, rule, due_date, days_past_due, dedupe, settings)


def _due_occurrence(rule, due_date, run_date):
    """Date this rule wants to fire on, if that date is today. Else None."""
    first_fire = add_days(due_date, cint(rule.offset_days))

    if getdate(first_fire) == run_date:
        return run_date

    if not rule.repeat_after_offset:
        return None

    every = cint(rule.repeat_every_days)
    if every < 1:
        return None

    elapsed = date_diff(run_date, first_fire)
    if elapsed <= 0 or elapsed % every:
        return None

    stop_after = cint(rule.stop_after_days)
    if stop_after and date_diff(run_date, due_date) > stop_after:
        return None

    return run_date


def _send(invoice, rule, due_date, days_past_due, dedupe, settings):
    recipient = rc.for_customer(invoice.customer)
    if not recipient:
        return

    doc = frappe.get_doc("Sales Invoice", invoice.name)

    notify(
        event=EVENT,
        doc=doc,
        channel=rule.channel or "Both",
        recipient=recipient,
        rule_label=rule.label,
        dedupe_key=dedupe,
        context={
            "outstanding": flt(invoice.outstanding_amount),
            "due_date": due_date,
            "days_overdue": max(days_past_due, 0),
            "rule_label": rule.label,
            "property_unit": rc.property_unit_label(linked_property_unit(invoice.name)),
        },
    )


@frappe.whitelist()
def send_reminder_now(invoice_name, channel=None):
    """Manual 'Send Payment Reminder' from the Sales Invoice form."""
    from frappe.utils import now

    frappe.has_permission("Sales Invoice", "read", doc=invoice_name, throw=True)

    settings = get_settings()
    if not settings or not settings.enabled:
        frappe.throw(frappe._("Property notifications are disabled in Property Notification Settings."))

    doc = frappe.get_doc("Sales Invoice", invoice_name)
    if doc.docstatus != 1:
        frappe.throw(frappe._("Submit the invoice first."))
    if flt(doc.outstanding_amount) <= 0:
        frappe.throw(frappe._("Invoice {0} is already settled.").format(invoice_name))

    due_date = getdate(doc.due_date)
    logs = notify(
        event=EVENT,
        doc=doc,
        channel=channel or "Both",
        recipient=rc.for_customer(doc.customer),
        rule_label="Manual",
        dedupe_key=f"payment-reminder::{invoice_name}::manual::{now()}",
        context={
            "outstanding": flt(doc.outstanding_amount),
            "due_date": due_date,
            "days_overdue": max(date_diff(getdate(today()), due_date), 0),
            "rule_label": "Manual",
            "property_unit": rc.property_unit_label(linked_property_unit(invoice_name)),
        },
    )
    return {"results": describe(logs)}
