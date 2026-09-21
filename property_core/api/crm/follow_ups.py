"""Property Follow Up — the activity trail that survives conversion.

The same record follows an enquiry from Lead to Opportunity to Booking, so the
history is never lost at a conversion. These endpoints are what the app's
"today's calls" screen and every "Log follow up" dialog talk to.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime, today

from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "reference_doctype",
    "reference_name",
    "party_name",
    "contact_number",
    "follow_up_type",
    "status",
    "scheduled_on",
    "assigned_to",
    "property",
    "property_unit",
    "outcome",
    "notes",
    "next_follow_up_on",
    "next_action",
    "completed_on",
    "completed_by",
    "owner",
    "creation",
]

WRITABLE = {
    "reference_doctype",
    "reference_name",
    "follow_up_type",
    "scheduled_on",
    "assigned_to",
    "status",
    "property",
    "property_unit",
    "outcome",
    "notes",
    "next_follow_up_on",
    "next_action",
}

OPEN_STATUSES = ["Open", "Rescheduled"]


@frappe.whitelist()
def get_follow_ups(
    reference_doctype=None,
    reference_name=None,
    status=None,
    assigned_to=None,
    follow_up_type=None,
    from_date=None,
    to_date=None,
    mine=None,
    search=None,
    order_by=None,
    page=1,
    page_size=20,
):
    user = base.require_user()

    conditions = []
    if reference_doctype:
        conditions.append(["reference_doctype", "=", reference_doctype])
    if reference_name:
        conditions.append(["reference_name", "=", reference_name])
    if status:
        statuses = base.parse(status, default=status)
        conditions.append(["status", "in", statuses if isinstance(statuses, list) else [statuses]])
    if assigned_to:
        conditions.append(["assigned_to", "=", assigned_to])
    if base.as_bool(mine):
        conditions.append(["assigned_to", "=", user])
    if follow_up_type:
        conditions.append(["follow_up_type", "=", follow_up_type])
    base.date_range(conditions, "scheduled_on", from_date, to_date)

    result = base.listing(
        "Property Follow Up",
        LIST_FIELDS,
        extra_filters=conditions,
        search=search,
        search_fields=["party_name", "contact_number", "reference_name", "notes"],
        order_by=order_by or "scheduled_on desc",
        page=page,
        page_size=page_size,
    )
    names = base.user_names([row.get("assigned_to") for row in result["rows"]])
    for row in result["rows"]:
        row["assigned_to_name"] = names.get(row.get("assigned_to"))
    return ok(data=result)


@frappe.whitelist()
def get_follow_up(name):
    doc = base.read_doc("Property Follow Up", name)
    return ok(data=base.doc_payload(doc))


@frappe.whitelist()
def create_follow_up(
    reference_doctype,
    reference_name,
    follow_up_type="Call",
    scheduled_on=None,
    assigned_to=None,
    notes=None,
    status="Open",
    property=None,
    property_unit=None,
):
    """Schedule the next touch. Party name, number and property are pulled off
    the reference by the doctype itself, so the client need not send them."""
    user = base.require_user()

    doc = frappe.new_doc("Property Follow Up")
    doc.update(
        {
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "follow_up_type": follow_up_type,
            "status": status,
            "scheduled_on": get_datetime(scheduled_on) if scheduled_on else now_datetime(),
            "assigned_to": assigned_to or user,
            "notes": notes,
            "property": property,
            "property_unit": property_unit,
        }
    )
    doc.insert()
    return ok(data=base.doc_payload(doc), message=_("Follow up scheduled"))


@frappe.whitelist()
def log_follow_up(
    reference_doctype,
    reference_name,
    follow_up_type="Call",
    outcome=None,
    notes=None,
    next_follow_up_on=None,
    next_action=None,
    assigned_to=None,
):
    """Record a call that already happened, and optionally book the next one.

    Same entry point the desk dialog uses, so a call logged from the app and a
    call logged from the desk end up identical.
    """
    base.require_user()
    from property_core.property_core.doctype.property_follow_up.property_follow_up import (
        log_follow_up as _log,
    )

    name = _log(
        reference_doctype=reference_doctype,
        reference_name=reference_name,
        follow_up_type=follow_up_type,
        outcome=outcome,
        notes=notes,
        next_follow_up_on=next_follow_up_on,
        next_action=next_action,
        assigned_to=assigned_to,
        status="Completed",
    )
    return ok(data=base.doc_payload(frappe.get_doc("Property Follow Up", name)), message=_("Logged"))


@frappe.whitelist()
def complete_follow_up(name, outcome=None, notes=None, next_follow_up_on=None, next_action=None):
    """Close an open follow-up. A ``next_follow_up_on`` raises the next one
    automatically -- that chaining is what keeps a lead from going cold."""
    doc = base.read_doc("Property Follow Up", name)
    doc.check_permission("write")

    doc.status = "Completed"
    if outcome:
        doc.outcome = outcome
    if notes:
        doc.notes = notes
    if next_follow_up_on:
        doc.next_follow_up_on = get_datetime(next_follow_up_on)
    if next_action:
        doc.next_action = next_action
    doc.save()

    return ok(data=base.doc_payload(doc), message=_("Follow up completed"))


@frappe.whitelist()
def reschedule(name, scheduled_on, notes=None):
    doc = base.read_doc("Property Follow Up", name)
    doc.check_permission("write")

    doc.scheduled_on = get_datetime(scheduled_on)
    doc.status = "Rescheduled"
    if notes:
        doc.notes = notes
    doc.save()
    return ok(data=base.doc_payload(doc), message=_("Rescheduled"))


@frappe.whitelist()
def cancel_follow_up(name, reason=None):
    doc = base.read_doc("Property Follow Up", name)
    doc.check_permission("write")
    doc.status = "Cancelled"
    if reason:
        doc.notes = reason
    doc.save()
    return ok(data={"name": name, "status": doc.status})


@frappe.whitelist()
def my_agenda(date=None, days=7, user=None):
    """Overdue / today / upcoming, the way the home screen shows it."""
    caller = base.require_user()
    user = user or caller
    on = date or today()

    def rows(filters, order):
        return base.serialize(
            frappe.get_list(
                "Property Follow Up",
                filters=filters,
                fields=LIST_FIELDS,
                order_by=order,
                limit=100,
            )
        )

    open_status = ["status", "in", OPEN_STATUSES]
    mine = ["assigned_to", "=", user]

    overdue = rows([mine, open_status, ["scheduled_on", "<", on]], "scheduled_on asc")
    due_today = rows(
        [mine, open_status, ["scheduled_on", ">=", on], ["scheduled_on", "<", add_days(on, 1)]],
        "scheduled_on asc",
    )
    upcoming = rows(
        [
            mine,
            open_status,
            ["scheduled_on", ">=", add_days(on, 1)],
            ["scheduled_on", "<", add_days(on, int(days or 7))],
        ],
        "scheduled_on asc",
    )

    return ok(
        data={
            "date": str(on),
            "user": user,
            "overdue": overdue,
            "today": due_today,
            "upcoming": upcoming,
            "counts": {
                "overdue": len(overdue),
                "today": len(due_today),
                "upcoming": len(upcoming),
            },
        }
    )
