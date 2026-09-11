"""
What maintenance has been done, what is due next, and inspection results.

"Work done" is the Work Order trail; "schedule" is what the unit's Maintenance
Plan Template will bill and service next. Money for maintenance lives in
``billing.maintenance_charges`` -- this module is about the work itself.
"""

import frappe
from frappe.utils import add_months, flt, getdate

from property_core.api.portal.base import (
    as_int,
    assert_unit,
    child_rows,
    customer_units,
    get_customer,
    get_list,
    scope,
    serialize,
)
from property_core.api.utils import ok
from property_core.property_operations.doctype.work_order_update.work_order_update import (
    proof_files,
)
from property_core.property_operations.utils.maintenance_schedule import project_schedule


@frappe.whitelist()
def work_history(property_unit=None, status=None, limit=100):
    """Every Work Order raised on the customer's units -- open and completed.

    This is the "kya kaam hua" feed: each row carries the linked complaint,
    who it was scheduled for, when it finished and what it cost the estate.
    """
    customer = get_customer()

    filters = scope(customer, property_unit)
    if filters is None:
        return ok(data={"work_orders": [], "summary": _empty_summary(), "total": 0})
    if status:
        filters["status"] = status

    rows = get_list(
        "Work Order", filters,
        order_by="coalesce(completed_date, scheduled_date, creation) desc",
        limit_page_length=as_int(limit, 100),
    )
    for row in rows:
        if row.get("property_unit"):
            row["unit_number"] = frappe.db.get_value(
                "Property Unit", row["property_unit"], "unit_number"
            )
        if row.get("issue"):
            row["issue_details"] = serialize(frappe.db.get_value(
                "Issue", row["issue"], ["subject", "status", "opening_date"], as_dict=True
            ))

    summary = _empty_summary()
    for row in rows:
        summary["by_status"][row.get("status") or "Unknown"] = (
            summary["by_status"].get(row.get("status") or "Unknown", 0) + 1
        )
        if row.get("status") == "Completed":
            summary["completed"] += 1
        else:
            summary["open"] += 1
        summary["total_cost"] += flt(row.get("actual_cost"))

    return ok(data={"work_orders": rows, "summary": summary, "total": len(rows)})


def _empty_summary():
    return {"completed": 0, "open": 0, "total_cost": 0.0, "by_status": {}}


@frappe.whitelist()
def schedule(property_unit=None):
    """Every maintenance charge on the customer's units -- billed and to come.

    The customer should see what they are signed up for the moment the unit is
    theirs, not after the first night's billing run. So this projects the plan
    itself: fixed rows and the repeat cycle expanded into real dates, each one
    marked Billed, Due, Upcoming or Paused.

    It shares project_schedule with the desk and the biller, so the portal, the
    unit form and the invoices cannot tell the customer three different stories.
    """
    customer = get_customer()

    units = [property_unit] if property_unit else customer_units(customer)
    if property_unit:
        assert_unit(customer, property_unit)
    if not units:
        return ok(data={"schedule": [], "total": 0, "summary": _empty_schedule_summary()})

    rows = []
    for unit_name in units:
        rows.extend(project_schedule(unit_name))

    rows.sort(key=lambda r: r["due_date"])

    summary = _empty_schedule_summary()
    for row in rows:
        summary["by_status"][row["status"]] = summary["by_status"].get(row["status"], 0) + 1
        if row["status"] == "Billed":
            summary["billed"] += row["amount"]
            summary["outstanding"] += flt(row.get("outstanding"))
        else:
            summary["upcoming"] += row["amount"]

    next_due = next((r for r in rows if r["status"] in ("Due", "Upcoming")), None)
    summary["next_due_date"] = next_due["due_date"] if next_due else None
    summary["next_due_amount"] = next_due["amount"] if next_due else 0

    return ok(data={"schedule": rows, "total": len(rows), "summary": summary})


def _empty_schedule_summary():
    return {
        "billed": 0.0,
        "outstanding": 0.0,
        "upcoming": 0.0,
        "next_due_date": None,
        "next_due_amount": 0,
        "by_status": {},
    }


@frappe.whitelist()
def inspections(property_unit=None, limit=20):
    """Inspection checklists carried out on the customer's units, with line items."""
    customer = get_customer()

    filters = scope(customer, property_unit)
    if filters is None:
        return ok(data={"inspections": [], "total": 0})

    rows = get_list(
        "Inspection Checklist", filters,
        order_by="inspection_date desc", limit_page_length=as_int(limit, 20),
    )
    for row in rows:
        row["items"] = child_rows(
            "Inspection Checklist Item", row["name"], parenttype="Inspection Checklist"
        )
        if row.get("property_unit"):
            row["unit_number"] = frappe.db.get_value(
                "Property Unit", row["property_unit"], "unit_number"
            )

    return ok(data={"inspections": rows, "total": len(rows)})


@frappe.whitelist()
def work_updates(work_order=None, property_unit=None, limit=100):
    """Progress reported from site, with the photos and video proving it.

    This is the "kitna kaam hua" feed. A customer sees it only for their own
    units -- the same scoping every other portal endpoint uses.
    """
    customer = get_customer()

    filters = scope(customer, property_unit)
    if filters is None:
        return ok(data={"updates": [], "total": 0})

    if work_order:
        owned = frappe.db.get_value("Work Order", work_order, "property_unit")
        if not owned or owned not in customer_units(customer):
            frappe.throw(frappe._("This work order is not on one of your units."))
        filters = {"work_order": work_order}

    rows = get_list(
        "Work Order Update", filters,
        order_by="posted_on desc",
        limit_page_length=as_int(limit, 100),
    )

    for row in rows:
        row["posted_by_name"] = frappe.db.get_value(
            "User", row.get("posted_by"), "full_name"
        ) or row.get("posted_by")
        row["proof"] = serialize_proof(proof_files(row["name"]))
        if row.get("property_unit"):
            row["unit_number"] = frappe.db.get_value(
                "Property Unit", row["property_unit"], "unit_number"
            )

    latest = rows[0] if rows else None

    return ok(data={
        "updates": rows,
        "total": len(rows),
        "latest_progress": flt(latest.get("progress")) if latest else 0,
    })


def serialize_proof(files):
    return [serialize(row) for row in files]
