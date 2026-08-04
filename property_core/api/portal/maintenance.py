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
    """Upcoming maintenance for the customer's units, from their plan template.

    Reads the template attached to each unit: fixed schedule rows first, then
    the repeat cycle. Periods already invoiced are marked ``billed``.
    """
    customer = get_customer()

    units = [property_unit] if property_unit else customer_units(customer)
    if property_unit:
        assert_unit(customer, property_unit)
    if not units:
        return ok(data={"schedule": [], "total": 0})

    out = []
    for unit_name in units:
        unit = frappe.db.get_value(
            "Property Unit", unit_name,
            ["name", "unit_number", "maintenance_plan_template", "maintenance_start_date",
             "pause_maintenance"],
            as_dict=True,
        )
        if not unit or not unit.get("maintenance_plan_template"):
            continue

        template = frappe.db.get_value(
            "Maintenance Plan Template", unit["maintenance_plan_template"],
            ["name", "template_name", "disabled", "repeat_every_n_months", "repeat_amount"],
            as_dict=True,
        )
        if not template or template.get("disabled"):
            continue

        billed_periods = set(
            frappe.get_all(
                "Sales Invoice",
                filters={"property_unit": unit_name, "docstatus": 1,
                         "maintenance_period": ["is", "set"]},
                pluck="maintenance_period",
            )
        )

        start = getdate(unit.get("maintenance_start_date")) if unit.get("maintenance_start_date") else None
        for row in child_rows("Maintenance Schedule Row", template["name"],
                              parenttype="Maintenance Plan Template"):
            due = row.get("fixed_due_date")
            if not due and start and row.get("month_no"):
                due = str(add_months(start, int(row["month_no"]) - 1))
            period = str(due)[:7] if due else None
            out.append({
                "property_unit": unit_name,
                "unit_number": unit.get("unit_number"),
                "template": template["template_name"],
                "kind": "Scheduled",
                "description": row.get("description"),
                "month_no": row.get("month_no"),
                "amount": flt(row.get("amount")),
                "due_date": due,
                "period": period,
                "billed": 1 if (period and period in billed_periods) else 0,
                "paused": 1 if unit.get("pause_maintenance") else 0,
            })

        if template.get("repeat_every_n_months"):
            out.append({
                "property_unit": unit_name,
                "unit_number": unit.get("unit_number"),
                "template": template["template_name"],
                "kind": "Recurring",
                "description": frappe._("Recurring maintenance every {0} month(s)").format(
                    template["repeat_every_n_months"]
                ),
                "month_no": None,
                "amount": flt(template.get("repeat_amount")),
                "due_date": None,
                "period": None,
                "billed": 0,
                "paused": 1 if unit.get("pause_maintenance") else 0,
            })

    out.sort(key=lambda r: (r.get("due_date") or "9999-12-31"))
    return ok(data={"schedule": out, "total": len(out)})


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
