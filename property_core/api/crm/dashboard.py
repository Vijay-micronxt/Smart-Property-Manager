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


# --------------------------------------------------------------------------- #
# view filters shared by the dashboards below
# --------------------------------------------------------------------------- #
#
# Every dashboard takes the same four knobs the JD frontend already sends to
# its old ``get_dashboard_data`` server script:
#
#   view_type    my | team | organisation
#   team_member  "a@x.com,b@y.com" -- narrows ``team``
#   date_range   all | today | yesterday | week | month | custom
#   date_from / date_to   for ``custom``
#
# ``my`` means records the user owns or is assigned; ``team`` the reporting
# tree (or the picked members of it); ``organisation`` everything the login
# may see. The permission engine is applied on top in every case, so a sales
# manager asking for ``organisation`` still only ever sees their own tree.

#: date fields a caller may filter the lead dashboard on
LEAD_DATE_FIELDS = ("creation", "modified", "custom_next_follow_up_date")

#: who "owns" a record, per doctype, for view_type=my/team
TARGET_FIELDS = {
    "Lead": "lead_owner",
    "Opportunity": "opportunity_owner",
    "Property Booking": "owner",
    "Property Follow Up": "assigned_to",
}


def _view(user, view_type, team_member):
    """(header, target users) -- target None = no owner filter, [] = nothing
    to show."""
    level = scope.scope_level(user)
    team = scope.team_members(user) if level != scope.OWN else []
    user_type = {scope.ALL: "admin", scope.TEAM: "supervisor"}.get(level, "regular")
    if level == scope.TEAM and not team:
        # a sales manager with nobody reporting to them works like an executive
        user_type = "regular"

    header = {"user_type": user_type, "view_type": view_type, "team_members": []}
    if user_type != "regular":
        names = base.user_names([user] + team)
        header["team_members"] = [{"user_id": u, "name": names.get(u) or u} for u in [user] + team]

    if view_type == "my":
        return header, [user]
    if view_type not in ("team", "organisation"):
        frappe.throw(frappe._("view_type must be my, team or organisation"))
    if user_type == "regular":
        return header, []
    if view_type == "organisation":
        return header, None

    requested = [u.strip() for u in (team_member or "").split(",") if u.strip()]
    if level == scope.ALL:
        return header, requested or None
    allowed = set([user] + team)
    return header, ([u for u in requested if u in allowed] if requested else sorted(allowed))


def _period(date_range, date_from=None, date_to=None):
    """(from, to-exclusive) for a date_range keyword; (None, None) for all."""
    now = today()
    if date_range == "today":
        return now, add_days(now, 1)
    if date_range == "yesterday":
        return add_days(now, -1), now
    if date_range == "week":
        return frappe.utils.get_first_day_of_week(now), None
    if date_range == "month":
        return get_first_day(now), None
    if date_range == "custom":
        return date_from or None, (add_days(date_to, 1) if date_to else None)
    return None, None


def _in_period(field, period):
    start, end = period
    out = []
    if start:
        out.append([field, ">=", start])
    if end:
        out.append([field, "<", end])
    return out


def _owned(doctype, target):
    """filters, or_filters that keep ``doctype`` to the target users -- owner
    field or an open assignment."""
    if target is None:
        return [], None
    field = TARGET_FIELDS[doctype]
    assigned = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doctype,
            "allocated_to": ["in", target],
            "status": ["in", ["Open", "Pending"]],
        },
        pluck="reference_name",
    )
    or_filters = [[field, "in", target]]
    if assigned:
        or_filters.append(["name", "in", list(set(assigned))])
    return [], or_filters


def _filters_echo(view_type, date_range, date_from, date_to, **extra):
    return {"view_type": view_type, "date_range": date_range, "date_from": date_from, "date_to": date_to, **extra}


# --------------------------------------------------------------------------- #
# lead dashboard -- drop-in for JD's "Dashboard api" server script
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def lead_dashboard(
    view_type="my", team_member=None, date_range="all", date_field="creation", date_from=None, date_to=None
):
    """Lead counts by status and source -- the exact shape JD's
    ``/api/method/get_dashboard_data`` server script returns, but read from
    ERPNext ``Lead`` (the one this app sells from), not Frappe CRM's
    ``CRM Lead``. The frontend swaps the URL and nothing else."""
    user = base.require_user()
    if date_field not in LEAD_DATE_FIELDS:
        frappe.throw(frappe._("date_field must be one of {0}").format(", ".join(LEAD_DATE_FIELDS)))

    header, target = _view(user, view_type, team_member)
    response = {
        "total_leads": 0,
        "pending_leads": 0,
        "status_counts": [],
        "source_counts": [],
        "filters": {},
        **header,
    }
    if target == []:
        return ok(data=response)

    _, or_filters = _owned("Lead", target)
    leads = frappe.get_list(
        "Lead",
        fields=["name", "custom_lead_status as status", "custom_lead_source as source", "modified"],
        filters=_in_period(date_field, _period(date_range, date_from, date_to)),
        or_filters=or_filters,
        limit_page_length=0,
    )

    cutoff = frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-24)
    response.update(
        {
            "total_leads": len(leads),
            "pending_leads": sum(1 for l in leads if l.status == "New" and l.modified and l.modified < cutoff),
            "status_counts": _count_by(leads, "status"),
            "source_counts": _count_by(leads, "source"),
            "filters": _filters_echo(view_type, date_range, date_from, date_to, date_field=date_field),
        }
    )
    return ok(data=response)


def _count_by(rows, field):
    counts = {}
    for row in rows:
        if row.get(field):
            counts[row[field]] = counts.get(row[field], 0) + 1
    return sorted(
        ({field: key, "count": value} for key, value in counts.items()), key=lambda r: r["count"], reverse=True
    )


# --------------------------------------------------------------------------- #
# the whole flow, lead to money, in one call
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def flow(view_type="my", team_member=None, date_range="month", date_from=None, date_to=None, project=None):
    """Overall status of the business, stage by stage:

        leads -> follow-ups -> opportunities -> customers -> bookings
              -> allocations -> invoices -> collections

    plus inventory and the stage-to-stage conversion. Counts inside the period
    are "new in the period" (lead created, opportunity opened, booking dated,
    invoice posted, payment received); pipeline numbers (open leads, overdue
    follow-ups, outstanding) are as of now.
    """
    user = base.require_user()
    header, target = _view(user, view_type, team_member)
    period = _period(date_range, date_from, date_to)
    properties = _project_properties(project) if project else None

    data = {**header, "filters": _filters_echo(view_type, date_range, date_from, date_to, project=project)}
    if target == []:
        return ok(data=data)

    leads = _flow_leads(target, period, project)
    follow_ups = _flow_follow_ups(target)
    opportunities = _flow_opportunities(target, period, project)
    bookings, booking_names = _flow_bookings(target, period, properties)
    money = _flow_money(booking_names, period)
    allocations = _flow_allocations(booking_names)

    data.update(
        {
            "leads": leads,
            "follow_ups": follow_ups,
            "opportunities": opportunities,
            "customers": _flow_customers(booking_names, period),
            "bookings": bookings,
            "allocations": allocations,
            "money": money,
            "inventory": _flow_inventory(project),
            "conversion": {
                "lead_to_opportunity": _pct(opportunities["total"], leads["total"]),
                "opportunity_to_booking": _pct(bookings["from_opportunity"], opportunities["total"]),
                "lead_to_booking": _pct(bookings["from_lead"], leads["total"]),
                "collection_rate": _pct(money["collected"], money["billed"]),
            },
            "stages": [
                {"stage": "Leads", "count": leads["total"]},
                {"stage": "Opportunities", "count": opportunities["total"]},
                {"stage": "Bookings", "count": bookings["total"]},
                {"stage": "Confirmed", "count": bookings["confirmed"]},
                {"stage": "Allocated", "count": allocations["active"]},
                {"stage": "Fully paid", "count": money["fully_paid_bookings"]},
            ],
        }
    )
    return ok(data=data)


@frappe.whitelist()
def trend(view_type="my", team_member=None, months=6, project=None):
    """Month by month: new leads, opportunities, bookings, booked value and
    money collected -- the line chart under the flow."""
    user = base.require_user()
    header, target = _view(user, view_type, team_member)
    months = max(1, min(frappe.utils.cint(months) or 6, 24))
    start = frappe.utils.add_months(get_first_day(today()), -(months - 1))
    period = (start, None)

    buckets = []
    cursor = start
    for _ in range(months):
        buckets.append(str(cursor)[:7])
        cursor = frappe.utils.add_months(cursor, 1)
    rows = {b: {"month": b, "leads": 0, "opportunities": 0, "bookings": 0, "booked_value": 0.0, "collected": 0.0}
            for b in buckets}

    if target != []:
        properties = _project_properties(project) if project else None

        def bump(records, date_key, key, value_key=None):
            for r in records:
                month = str(r.get(date_key) or "")[:7]
                if month in rows:
                    rows[month][key] += flt(r.get(value_key)) if value_key else 1

        _, lead_or = _owned("Lead", target)
        lead_filters = _in_period("creation", period)
        if project and _has_field("Lead", "custom_project"):
            lead_filters.append(["custom_project", "=", project])
        bump(frappe.get_list("Lead", filters=lead_filters, or_filters=lead_or, fields=["creation"],
                             limit_page_length=0), "creation", "leads")

        _, opp_or = _owned("Opportunity", target)
        opp_filters = _in_period("creation", period)
        if project:
            opp_filters.append(["custom_project", "=", project])
        bump(frappe.get_list("Opportunity", filters=opp_filters, or_filters=opp_or, fields=["creation"],
                             limit_page_length=0), "creation", "opportunities")

        booked, names = _booking_rows(target, period, properties)
        confirmed = [b for b in booked if b.docstatus == 1]
        bump(booked, "booking_date", "bookings")
        bump(confirmed, "booking_date", "booked_value", "total_price")

        for payment in _payments_for(_invoices_of(names), period):
            month = str(payment.posting_date)[:7]
            if month in rows:
                rows[month]["collected"] += flt(payment.allocated_amount)

    return ok(data={**header, "months": [rows[b] for b in buckets]})


# --- flow sections ----------------------------------------------------------- #

def _flow_leads(target, period, project):
    _, or_filters = _owned("Lead", target)
    filters = []
    if project and _has_field("Lead", "custom_project"):
        filters.append(["custom_project", "=", project])
    new = frappe.get_list(
        "Lead",
        filters=filters + _in_period("creation", period),
        or_filters=or_filters,
        fields=["custom_lead_status as status", "custom_lead_source as source", "status as erpnext_status"],
        limit_page_length=0,
    )
    open_now = frappe.get_list(
        "Lead",
        filters=filters + [["status", "not in", ["Converted", "Do Not Contact", "Opportunity"]]],
        or_filters=or_filters,
        fields=["count(name) as total"],
    )
    untouched = frappe.get_list(
        "Lead",
        filters=filters
        + [["custom_next_follow_up_date", "is", "not set"], ["status", "not in", ["Converted", "Do Not Contact"]]],
        or_filters=or_filters,
        fields=["count(name) as total"],
    )
    return {
        "total": len(new),
        "converted": sum(1 for l in new if l.erpnext_status in ("Converted", "Opportunity")),
        "open_now": open_now[0].total if open_now else 0,
        "without_follow_up": untouched[0].total if untouched else 0,
        "by_status": _count_by(new, "status"),
        "by_source": _count_by(new, "source"),
    }


def _flow_follow_ups(target):
    _, or_filters = _owned("Property Follow Up", target)
    now = today()
    rows = frappe.get_list(
        "Property Follow Up",
        filters=[["status", "in", ["Open", "Rescheduled"]]],
        or_filters=or_filters,
        fields=["scheduled_on"],
        limit_page_length=0,
    )
    today_d, tomorrow = frappe.utils.getdate(now), frappe.utils.getdate(add_days(now, 1))
    due = [frappe.utils.getdate(r.scheduled_on) for r in rows if r.scheduled_on]
    return {
        "open": len(rows),
        "overdue": sum(1 for d in due if d < today_d),
        "today": sum(1 for d in due if d == today_d),
        "upcoming": sum(1 for d in due if d >= tomorrow),
    }


def _flow_opportunities(target, period, project):
    _, or_filters = _owned("Opportunity", target)
    filters = _in_period("creation", period)
    if project:
        filters.append(["custom_project", "=", project])
    rows = frappe.get_list(
        "Opportunity",
        filters=filters,
        or_filters=or_filters,
        fields=["status", "opportunity_amount"],
        limit_page_length=0,
    )
    by_status = {}
    for r in rows:
        entry = by_status.setdefault(r.status, {"status": r.status, "count": 0, "value": 0.0})
        entry["count"] += 1
        entry["value"] = flt(entry["value"] + flt(r.opportunity_amount), 2)
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r.status not in ("Converted", "Lost", "Closed")),
        "won": sum(1 for r in rows if r.status == "Converted"),
        "lost": sum(1 for r in rows if r.status == "Lost"),
        "pipeline_value": flt(sum(flt(r.opportunity_amount) for r in rows if r.status not in ("Converted", "Lost", "Closed")), 2),
        "by_status": sorted(by_status.values(), key=lambda e: e["count"], reverse=True),
    }


def _booking_rows(target, period, properties):
    _, or_filters = _owned("Property Booking", target)
    filters = [["docstatus", "<", 2]] + _in_period("booking_date", period)
    if properties is not None:
        filters.append(["unit_property", "in", properties])
    rows = frappe.get_list(
        "Property Booking",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name", "customer", "booking_status", "docstatus", "total_price", "booking_amount",
            "booking_date", "opportunity", "lead",
        ],
        limit_page_length=0,
    )
    return rows, [r.name for r in rows]


def _flow_bookings(target, period, properties):
    rows, names = _booking_rows(target, period, properties)
    confirmed = [r for r in rows if r.docstatus == 1]
    return (
        {
            "total": len(rows),
            "draft": sum(1 for r in rows if r.docstatus == 0),
            "confirmed": len(confirmed),
            # walk-ins never had an opportunity; conversion counts only the funnel
            "from_opportunity": sum(1 for r in confirmed if r.opportunity),
            "from_lead": sum(1 for r in confirmed if r.lead),
            "walk_in": sum(1 for r in confirmed if not (r.opportunity or r.lead)),
            "booked_value": flt(sum(flt(r.total_price) for r in confirmed), 2),
            "booking_amount": flt(sum(flt(r.booking_amount) for r in confirmed), 2),
            "by_status": _count_by(rows, "booking_status"),
        },
        [r.name for r in confirmed],
    )


def _flow_customers(booking_names, period):
    new = frappe.get_list("Customer", filters=_in_period("creation", period), fields=["count(name) as total"]) \
        if base.can_read("Customer") else []
    booked = set(
        frappe.get_all("Property Booking", filters={"name": ["in", booking_names or [""]]}, pluck="customer")
    )
    return {"new": new[0].total if new else 0, "with_booking": len(booked)}


def _flow_allocations(booking_names):
    if not base.can_read("Property Allocation") or not booking_names:
        return {"active": 0, "draft": 0, "pending_allocation": len(booking_names or [])}
    rows = frappe.get_list(
        "Property Allocation",
        filters={"booking": ["in", booking_names], "docstatus": ["<", 2]},
        fields=["booking", "docstatus"],
        limit_page_length=0,
    )
    allocated = {r.booking for r in rows if r.docstatus == 1}
    return {
        "active": len(allocated),
        "draft": sum(1 for r in rows if r.docstatus == 0),
        "pending_allocation": len(set(booking_names) - allocated),
    }


def _invoices_of(booking_names):
    if not booking_names or not base.can_read("Payment Plan"):
        return []
    return [
        i
        for i in frappe.get_list("Payment Plan", filters={"booking": ["in", booking_names]}, pluck="invoice")
        if i
    ]


def _payments_for(invoices, period):
    if not invoices or not base.can_read("Payment Entry"):
        return []
    filters = [
        ["Payment Entry Reference", "reference_doctype", "=", "Sales Invoice"],
        ["Payment Entry Reference", "reference_name", "in", invoices],
        ["docstatus", "=", 1],
    ] + _in_period("posting_date", period)
    return frappe.get_list(
        "Payment Entry",
        filters=filters,
        fields=["name", "posting_date", "`tabPayment Entry Reference`.allocated_amount as allocated_amount"],
        limit_page_length=0,
    )


def _flow_money(booking_names, period):
    """Billed / collected / outstanding for the confirmed bookings in view,
    plus what fell overdue and what falls due in the next 30 days."""
    empty = {
        "billed": 0.0, "collected": 0.0, "outstanding": 0.0, "overdue": 0.0,
        "due_next_30_days": 0.0, "collected_in_period": 0.0, "unbilled_milestones": 0,
        "fully_paid_bookings": 0,
    }
    if not booking_names or not (base.can_read("Payment Plan") and base.can_read("Sales Invoice")):
        return empty

    plan = frappe.get_list(
        "Payment Plan",
        filters={"booking": ["in", booking_names]},
        fields=["booking", "amount", "due_date", "invoice"],
        limit_page_length=0,
    )
    invoices = {
        r.name: r
        for r in frappe.get_list(
            "Sales Invoice",
            filters={"name": ["in", [p.invoice for p in plan if p.invoice] or [""]], "docstatus": 1},
            fields=["name", "grand_total", "outstanding_amount", "due_date"],
            limit_page_length=0,
        )
    }
    now = frappe.utils.getdate(today())
    horizon = frappe.utils.getdate(add_days(now, 30))
    out = dict(empty)
    per_booking = {}
    for p in plan:
        inv = invoices.get(p.invoice)
        pending = flt(inv.outstanding_amount) if inv else flt(p.amount)
        per_booking[p.booking] = per_booking.get(p.booking, 0) + pending
        if not inv:
            out["unbilled_milestones"] += 1
        else:
            out["billed"] += flt(inv.grand_total)
            out["outstanding"] += flt(inv.outstanding_amount)
        due = frappe.utils.getdate(p.due_date) if p.due_date else None
        if due and pending > 0:
            if due < now:
                out["overdue"] += pending
            elif due <= horizon:
                out["due_next_30_days"] += pending
    out["collected"] = out["billed"] - out["outstanding"]
    out["collected_in_period"] = sum(flt(p.allocated_amount) for p in _payments_for(list(invoices), period))
    out["fully_paid_bookings"] = sum(1 for b, pending in per_booking.items() if pending <= 0.01)
    return {k: (flt(v, 2) if isinstance(v, float) else v) for k, v in out.items()}


def _flow_inventory(project=None):
    filters = {"property": ["in", _project_properties(project)]} if project else {}
    rows = frappe.get_list(
        "Property Unit",
        filters=filters,
        fields=["availability_status as status", "count(name) as total", "sum(base_price) as value"],
        group_by="availability_status",
    )
    return {
        "total_units": sum(r.total for r in rows),
        "by_status": [{"status": r.status, "count": r.total, "value": flt(r.value, 2)} for r in rows],
        "available": sum(r.total for r in rows if r.status == "Available"),
        "sold": sum(r.total for r in rows if r.status in ("Booked", "Allocated")),
        "available_value": flt(sum(flt(r.value) for r in rows if r.status == "Available"), 2),
    }


def _project_properties(project):
    return frappe.get_all("Property", filters={"project": project}, pluck="name") or [""]


def _has_field(doctype, fieldname):
    return bool(frappe.get_meta(doctype).has_field(fieldname))


def _pct(part, whole):
    return flt(part * 100.0 / whole, 1) if whole else 0.0
