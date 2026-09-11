"""Every maintenance charge a unit will carry, visible the moment it is booked.

The unit form used to list only invoices that had already been raised, so a
freshly booked unit said "No maintenance invoices generated yet" and the owner
had to wait for the nightly job to find out what they were signing up for.

This projects the same schedule the biller works from -- fixed rows, then the
repeat cycle expanded into real dates -- and marks each period Billed, Due or
Upcoming. It deliberately mirrors _bill_unit's rules rather than inventing its
own, so the table and the invoices can never disagree.
"""

import frappe
from frappe.utils import add_months, flt, getdate, today

DEFAULT_MONTHS_AHEAD = 24


def project_schedule(property_unit, months_ahead=DEFAULT_MONTHS_AHEAD):
    unit = frappe.db.get_value(
        "Property Unit",
        property_unit,
        ["name", "unit_number", "maintenance_plan_template", "maintenance_start_date",
         "pause_maintenance", "customer"],
        as_dict=True,
    )
    if not unit or not unit.get("maintenance_plan_template"):
        return []

    template = frappe.get_cached_doc("Maintenance Plan Template", unit.maintenance_plan_template)
    if template.disabled:
        return []

    settings_item = frappe.db.get_single_value("Property Core Settings", "maintenance_item_code")
    today_date = getdate(today())
    start = getdate(unit.maintenance_start_date) if unit.maintenance_start_date else None

    billed = {
        row.maintenance_period: row
        for row in frappe.get_all(
            "Sales Invoice",
            filters={"property_unit": property_unit, "docstatus": ["<", 2],
                     "maintenance_period": ["is", "set"]},
            fields=["name", "maintenance_period", "grand_total", "outstanding_amount", "status"],
        )
    }

    rows = []
    rows_by_month = {}
    max_month = 0

    for row in template.schedule:
        if row.fixed_due_date:
            due = getdate(row.fixed_due_date)
            rows.append(_entry(unit, due, str(due), row.amount,
                               row.description or "Maintenance charge",
                               row.item_code or settings_item, billed, today_date))
        elif row.month_no:
            rows_by_month[row.month_no] = row
            max_month = max(max_month, row.month_no)

    if start:
        horizon = _months_between(start, today_date) + months_ahead
        repeat_n = template.repeat_every_n_months or 0
        repeat_amt = flt(template.repeat_amount)
        repeat_item = template.repeat_item_code or settings_item

        for month in range(1, horizon + 1):
            row = rows_by_month.get(month)
            amount = flt(row.amount) if row else 0
            item = (row.item_code or settings_item) if row else settings_item
            description = row.description if row else None

            if not amount and repeat_n and repeat_amt and month > max_month:
                if (month - max_month) % repeat_n == 0:
                    amount = repeat_amt
                    item = repeat_item
                    description = f"Recurring maintenance (month {month})"

            if not amount:
                continue

            due = getdate(add_months(start, month - 1))
            rows.append(_entry(unit, due, "{}-{:02d}".format(due.year, due.month), amount,
                               description or "Maintenance charge", item, billed, today_date))

    rows.sort(key=lambda r: r["due_date"])
    return rows


def _entry(unit, due, period, amount, description, item_code, billed, today_date):
    invoice = billed.get(period)

    if invoice:
        status = "Billed"
    elif unit.get("pause_maintenance"):
        status = "Paused"
    elif due <= today_date:
        status = "Due"
    else:
        status = "Upcoming"

    return {
        "property_unit": unit.name,
        "unit_number": unit.get("unit_number"),
        "period": period,
        "due_date": str(due),
        "amount": flt(amount),
        "description": description,
        "item_code": item_code,
        "status": status,
        "invoice": invoice.name if invoice else None,
        "invoice_status": invoice.status if invoice else None,
        "outstanding": flt(invoice.outstanding_amount) if invoice else None,
    }


def _months_between(start, end):
    return max((end.year - start.year) * 12 + (end.month - start.month), 0)


@frappe.whitelist()
def unit_schedule(property_unit, months_ahead=DEFAULT_MONTHS_AHEAD):
    """What this unit will be charged, and what it already has been."""
    frappe.has_permission("Property Unit", "read", doc=property_unit, throw=True)

    rows = project_schedule(property_unit, int(months_ahead))

    return {
        "schedule": rows,
        "total_billed": sum(r["amount"] for r in rows if r["status"] == "Billed"),
        "total_outstanding": sum(flt(r["outstanding"]) for r in rows if r["invoice"]),
        "total_upcoming": sum(r["amount"] for r in rows if r["status"] in ("Due", "Upcoming")),
    }


@frappe.whitelist()
def bill_now(property_unit):
    """Raise whatever is already due on this unit, without waiting for the
    nightly run."""
    frappe.has_permission("Property Unit", "write", doc=property_unit, throw=True)

    from property_core.property_operations.utils.maintenance_billing import _bill_unit

    unit = frappe.get_doc("Property Unit", property_unit)
    if not unit.maintenance_plan_template:
        frappe.throw(frappe._("This unit has no maintenance plan."))

    before = frappe.db.count("Sales Invoice", {"property_unit": property_unit,
                                               "maintenance_period": ["is", "set"],
                                               "docstatus": ["<", 2]})
    _bill_unit(unit, getdate(today()))
    after = frappe.db.count("Sales Invoice", {"property_unit": property_unit,
                                              "maintenance_period": ["is", "set"],
                                              "docstatus": ["<", 2]})

    return {"raised": after - before, "schedule": project_schedule(property_unit)}
