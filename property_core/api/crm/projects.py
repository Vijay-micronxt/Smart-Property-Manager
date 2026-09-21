"""The project-centric roll-up.

JD does not run the business per lead or per booking — it runs it per
development. The project is created first, its properties and units are laid
out under it, and from then on every question asked in a review is "how is
Prashantha Vana doing": how much inventory is left, how many enquiries came
in, what got booked, how much money is in, what work is pending on site.

``overview`` answers all of that in one call; the rest are the same sections
on their own for screens that page through them.

Everything here respects the caller's scope — a sales executive looking at a
project sees the project's inventory (public to the floor) but only their own
leads, opportunities and bookings inside it.
"""

import frappe
from frappe import _
from frappe.utils import flt

from property_core.api.crm import base
from property_core.api.crm.inventory import unit_stats
from property_core.api.utils import ok

PROJECT_FIELDS = [
    "name",
    "project_name",
    "status",
    "customer",
    "company",
    "expected_start_date",
    "expected_end_date",
    "percent_complete",
    "project_type",
    "notes",
    "modified",
]


@frappe.whitelist()
def get_projects(search=None, status=None, page=1, page_size=20, order_by=None, with_stats=1):
    base.require_user()

    conditions = []
    if status:
        conditions.append(["status", "=", status])

    result = base.listing(
        "Project",
        PROJECT_FIELDS,
        extra_filters=conditions,
        search=search,
        search_fields=["project_name", "name"],
        order_by=order_by or "modified desc",
        page=page,
        page_size=page_size,
    )

    if base.as_bool(with_stats, True):
        for row in result["rows"]:
            row["summary"] = _headline(row["name"])

    return ok(data=result)


@frappe.whitelist()
def get_project(name):
    doc = base.read_doc("Project", name)
    payload = base.doc_payload(doc)
    payload["summary"] = _headline(name)
    payload["properties"] = base.serialize(
        frappe.get_list(
            "Property",
            filters={"project": name},
            fields=["name", "property_name", "property_type", "status", "total_area"],
            order_by="property_name asc",
        )
    )
    return ok(data=payload)


@frappe.whitelist()
def overview(name, from_date=None, to_date=None):
    """Everything about one development, in one request."""
    base.read_doc("Project", name)
    properties = _properties_of(name)

    return ok(
        data={
            "project": base.serialize(
                frappe.db.get_value("Project", name, PROJECT_FIELDS, as_dict=True)
            ),
            "inventory": _inventory(name, properties),
            "funnel": _funnel(name, properties, from_date, to_date),
            "sales": _sales(name, properties, from_date, to_date),
            "money": _money(name, properties),
            "operations": _operations(properties),
            "team": _team(name, properties),
        }
    )


@frappe.whitelist()
def project_inventory(name):
    base.read_doc("Project", name)
    properties = _properties_of(name)
    return ok(
        data={
            "summary": _inventory(name, properties),
            "properties": [
                {**row, "units": unit_stats([row["name"]]).get(row["name"], {})}
                for row in frappe.get_list(
                    "Property",
                    filters={"project": name},
                    fields=["name", "property_name", "property_type", "status"],
                )
            ],
        }
    )


@frappe.whitelist()
def project_funnel(name, from_date=None, to_date=None):
    base.read_doc("Project", name)
    return ok(data=_funnel(name, _properties_of(name), from_date, to_date))


@frappe.whitelist()
def project_bookings(name, page=1, page_size=20):
    """Bookings under the development, newest first."""
    base.read_doc("Project", name)
    properties = _properties_of(name)

    result = base.listing(
        "Property Booking",
        [
            "name",
            "customer",
            "property_unit",
            "unit_property",
            "booking_status",
            "booking_date",
            "total_price",
            "booking_amount",
            "docstatus",
            "owner",
        ],
        extra_filters=[["unit_property", "in", properties], ["docstatus", "<", 2]],
        order_by="booking_date desc",
        page=page,
        page_size=page_size,
    )
    return ok(data=result)


@frappe.whitelist()
def project_operations(name):
    base.read_doc("Project", name)
    return ok(data=_operations(_properties_of(name)))


@frappe.whitelist()
def project_activity(name, limit=30):
    """The last things that happened on this development, across doctypes —
    what a manager opens the project to see."""
    base.read_doc("Project", name)
    properties = _properties_of(name)
    units = _units_of(properties)

    events = []

    for row in frappe.get_list(
        "Property Booking",
        filters={"unit_property": ["in", properties], "docstatus": ["<", 2]},
        fields=["name", "customer", "property_unit", "booking_status", "modified", "owner"],
        order_by="modified desc",
        limit=limit,
    ):
        events.append(
            {
                "type": "Booking",
                "reference": row.name,
                "title": _("{0} — {1}").format(row.property_unit, row.customer),
                "status": row.booking_status,
                "on": row.modified,
                "user": row.owner,
            }
        )

    for row in frappe.get_list(
        "Opportunity",
        filters={"custom_project": name},
        fields=["name", "party_name", "status", "modified", "opportunity_owner"],
        order_by="modified desc",
        limit=limit,
    ):
        events.append(
            {
                "type": "Opportunity",
                "reference": row.name,
                "title": row.party_name,
                "status": row.status,
                "on": row.modified,
                "user": row.opportunity_owner,
            }
        )

    if units and _readable("Work Order", "property_unit"):
        for row in frappe.get_list(
            "Work Order",
            filters={"property_unit": ["in", units]},
            fields=["name", "work_type", "status", "modified", "property_unit"],
            order_by="modified desc",
            limit=limit,
        ):
            events.append(
                {
                    "type": "Work Order",
                    "reference": row.name,
                    "title": _("{0} on {1}").format(row.work_type or _("Work"), row.property_unit),
                    "status": row.status,
                    "on": row.modified,
                    "user": None,
                }
            )

    events.sort(key=lambda e: e["on"], reverse=True)
    return ok(data=base.serialize(events[: int(limit)]))


# --------------------------------------------------------------------------- #

def _headline(project):
    properties = _properties_of(project)
    stats = unit_stats(properties)

    totals = {"total": 0, "available": 0, "booked": 0, "reserved": 0, "allocated": 0, "value": 0.0}
    for entry in stats.values():
        for key in totals:
            totals[key] = flt(totals[key] + entry.get(key, 0), 2)

    bookings = frappe.get_list(
        "Property Booking",
        filters=[["unit_property", "in", properties], ["docstatus", "=", 1]],
        fields=["count(name) as total", "sum(total_price) as value"],
    )
    booking_row = bookings[0] if bookings else {}

    return {
        "properties": len(properties) if properties != [""] else 0,
        "units": totals["total"],
        "available_units": totals["available"],
        "booked_units": totals["booked"] + totals["allocated"],
        "inventory_value": totals["value"],
        "bookings": booking_row.get("total") or 0,
        "booked_value": flt(booking_row.get("value"), 2),
    }


def _inventory(project, properties):
    stats = unit_stats(properties)
    summary = _headline(project)
    summary["by_property"] = stats
    return summary


def _funnel(project, properties, from_date, to_date):
    lead_filters = [["custom_property", "in", properties]]
    base.date_range(lead_filters, "creation", from_date, to_date)
    leads = frappe.get_list(
        "Lead",
        filters=lead_filters,
        fields=["custom_lead_status as status", "count(name) as total"],
        group_by="custom_lead_status",
    )

    opportunity_filters = [["custom_project", "=", project]]
    base.date_range(opportunity_filters, "transaction_date", from_date, to_date)
    opportunities = frappe.get_list(
        "Opportunity",
        filters=opportunity_filters,
        fields=["status", "count(name) as total", "sum(opportunity_amount) as value"],
        group_by="status",
    )

    follow_ups = frappe.get_list(
        "Property Follow Up",
        filters=[["property", "in", properties], ["status", "in", ["Open", "Rescheduled"]]],
        fields=["count(name) as total"],
    )

    return {
        "leads": {
            "total": sum(row.total for row in leads),
            "by_status": leads,
        },
        "opportunities": {
            "total": sum(row.total for row in opportunities),
            "value": flt(sum(flt(row.value) for row in opportunities), 2),
            "by_status": opportunities,
        },
        "open_follow_ups": (follow_ups[0].total if follow_ups else 0),
    }


def _sales(project, properties, from_date, to_date):
    filters = [["unit_property", "in", properties], ["docstatus", "<", 2]]
    base.date_range(filters, "booking_date", from_date, to_date)

    rows = frappe.get_list(
        "Property Booking",
        filters=filters,
        fields=["booking_status", "count(name) as total", "sum(total_price) as value"],
        group_by="booking_status",
    )
    return {
        "bookings": sum(row.total for row in rows),
        "value": flt(sum(flt(row.value) for row in rows), 2),
        "by_status": rows,
    }


def _money(project, properties):
    """Billed and collected against this development's units."""
    units = _units_of(properties)
    if not units or not _readable("Sales Invoice", "property_unit"):
        return {"billed": 0.0, "collected": 0.0, "outstanding": 0.0, "invoices": 0}

    rows = frappe.get_list(
        "Sales Invoice",
        filters={"property_unit": ["in", units], "docstatus": 1},
        fields=[
            "count(name) as invoices",
            "sum(grand_total) as billed",
            "sum(outstanding_amount) as outstanding",
        ],
    )
    row = rows[0] if rows else {}
    billed = flt(row.get("billed"))
    outstanding = flt(row.get("outstanding"))
    return {
        "invoices": row.get("invoices") or 0,
        "billed": flt(billed, 2),
        "collected": flt(billed - outstanding, 2),
        "outstanding": flt(outstanding, 2),
    }


def _operations(properties):
    units = _units_of(properties)
    out = {
        "work_orders": {"total": 0, "by_status": []},
        "issues": {"total": 0, "by_status": []},
        "tasks": {"total": 0, "by_status": []},
    }
    if not units:
        return out

    if _readable("Work Order", "property_unit"):
        rows = frappe.get_list(
            "Work Order",
            filters={"property_unit": ["in", units]},
            fields=["status", "count(name) as total"],
            group_by="status",
        )
        out["work_orders"] = {"total": sum(r.total for r in rows), "by_status": rows}

    if _readable("Issue", "property_unit"):
        rows = frappe.get_list(
            "Issue",
            filters={"property_unit": ["in", units]},
            fields=["status", "count(name) as total"],
            group_by="status",
        )
        out["issues"] = {"total": sum(r.total for r in rows), "by_status": rows}

    return out


def _team(project, properties):
    """Who is working this development — owners of its live opportunities."""
    rows = frappe.get_list(
        "Opportunity",
        filters=[["custom_project", "=", project], ["status", "not in", ["Lost", "Closed"]]],
        fields=["opportunity_owner", "count(name) as total", "sum(opportunity_amount) as value"],
        group_by="opportunity_owner",
        order_by="total desc",
    )
    names = base.user_names([row.opportunity_owner for row in rows])
    return [
        {
            "user": row.opportunity_owner,
            "full_name": names.get(row.opportunity_owner),
            "open_opportunities": row.total,
            "value": flt(row.value, 2),
        }
        for row in rows
    ]


def _properties_of(project):
    return frappe.get_list("Property", filters={"project": project}, pluck="name") or [""]


def _units_of(properties):
    if not properties:
        return []
    return frappe.get_list("Property Unit", filters={"property": ["in", properties]}, pluck="name")


def _has_field(doctype, fieldname):
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.get_meta(doctype).get_field(fieldname))


def _readable(doctype, fieldname=None):
    """A section the caller cannot read is left out of the roll-up, not thrown.

    Sales staff hold no permission on Work Order, Issue or Sales Invoice on
    most sites, and a project overview that 403s for the whole floor because
    of one section nobody asked for is worse than one that omits it.
    """
    if fieldname and not _has_field(doctype, fieldname):
        return False
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.has_permission(doctype, "read"))
