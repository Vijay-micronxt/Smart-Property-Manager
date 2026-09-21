"""The home screen: what this login should do today, and how they are doing.

Numbers are whatever the caller is allowed to see — an executive gets their
own, a manager gets their team's, an admin gets the company's — because every
query below goes through the same permission engine as the lists.
"""

import frappe
from frappe.utils import add_days, flt, get_first_day, get_last_day, today

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_core.crm import scope


@frappe.whitelist()
def summary(from_date=None, to_date=None):
    user = base.require_user()
    from_date = from_date or get_first_day(today())
    to_date = to_date or get_last_day(today())

    return ok(
        data={
            "user": user,
            "scope": scope.scope_level(user),
            "period": {"from_date": str(from_date), "to_date": str(to_date)},
            "today": _today_counts(user),
            "leads": _leads(from_date, to_date),
            "opportunities": _opportunities(from_date, to_date),
            "bookings": _bookings(from_date, to_date),
            "conversion": _conversion(from_date, to_date),
            "projects": _top_projects(),
        }
    )


def _today_counts(user):
    now = today()
    open_status = ["status", "in", ["Open", "Rescheduled"]]

    def count(filters):
        rows = frappe.get_list("Property Follow Up", filters=filters, fields=["count(name) as total"])
        return rows[0].total if rows else 0

    return {
        "follow_ups_overdue": count([["assigned_to", "=", user], open_status, ["scheduled_on", "<", now]]),
        "follow_ups_today": count(
            [
                ["assigned_to", "=", user],
                open_status,
                ["scheduled_on", ">=", now],
                ["scheduled_on", "<", add_days(now, 1)],
            ]
        ),
        "leads_untouched": _untouched_leads(user),
    }


def _untouched_leads(user):
    """Leads owned by this user with no follow-up scheduled — the ones that go
    cold without anybody noticing."""
    rows = frappe.get_list(
        "Lead",
        filters=[
            ["custom_follow_up_owner", "=", user],
            ["custom_next_follow_up_date", "is", "not set"],
            ["status", "not in", ["Converted", "Do Not Contact"]],
        ],
        fields=["count(name) as total"],
    )
    return rows[0].total if rows else 0


def _leads(from_date, to_date):
    filters = []
    base.date_range(filters, "creation", from_date, to_date)
    rows = frappe.get_list(
        "Lead",
        filters=filters,
        fields=["custom_lead_status as status", "count(name) as total"],
        group_by="custom_lead_status",
        order_by="total desc",
    )
    return {"total": sum(row.total for row in rows), "by_status": rows[:10]}


def _opportunities(from_date, to_date):
    filters = []
    base.date_range(filters, "transaction_date", from_date, to_date)
    rows = frappe.get_list(
        "Opportunity",
        filters=filters,
        fields=["status", "count(name) as total", "sum(opportunity_amount) as value"],
        group_by="status",
    )
    return {
        "total": sum(row.total for row in rows),
        "value": flt(sum(flt(row.value) for row in rows), 2),
        "by_status": rows,
    }


def _bookings(from_date, to_date):
    filters = [["docstatus", "<", 2]]
    base.date_range(filters, "booking_date", from_date, to_date)
    rows = frappe.get_list(
        "Property Booking",
        filters=filters,
        fields=["booking_status", "docstatus", "count(name) as total", "sum(total_price) as value"],
        group_by="booking_status, docstatus",
    )
    confirmed = [row for row in rows if row.docstatus == 1]
    return {
        "total": sum(row.total for row in rows),
        "confirmed": sum(row.total for row in confirmed),
        "value": flt(sum(flt(row.value) for row in confirmed), 2),
        "by_status": rows,
    }


def _conversion(from_date, to_date):
    leads = _leads(from_date, to_date)["total"]
    opportunities = _opportunities(from_date, to_date)["total"]
    bookings = _bookings(from_date, to_date)["confirmed"]
    return {
        "lead_to_opportunity": flt(opportunities * 100.0 / leads, 1) if leads else 0.0,
        "opportunity_to_booking": flt(bookings * 100.0 / opportunities, 1) if opportunities else 0.0,
        "lead_to_booking": flt(bookings * 100.0 / leads, 1) if leads else 0.0,
    }


def _top_projects(limit=5):
    """Where this login's pipeline actually sits."""
    rows = frappe.get_list(
        "Opportunity",
        filters=[["status", "not in", ["Lost", "Closed"]], ["custom_project", "is", "set"]],
        fields=["custom_project as project", "count(name) as opportunities", "sum(opportunity_amount) as value"],
        group_by="custom_project",
        order_by="value desc",
        limit=limit,
    )
    names = {
        row.name: row.project_name
        for row in frappe.get_list(
            "Project",
            filters={"name": ["in", [r.project for r in rows] or [""]]},
            fields=["name", "project_name"],
        )
    }
    for row in rows:
        row["project_name"] = names.get(row.project)
        row["value"] = flt(row.value, 2)
    return rows
