"""Open a maintenance task a few days before each maintenance date.

The dates come from ``project_schedule`` -- the same projection the biller,
the unit form and the portal read -- so a task exists for exactly the periods
that are (or will be) charged. One task per unit per period: re-running adds
nothing, and a task someone cancelled is not re-opened.

Runs from the daily maintenance job and whenever a booking starts maintenance.
Periods that fell due more than ``BACKFILL_DAYS`` ago are left alone, so
switching this on does not flood the team with visits for months already past.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from property_core.property_operations.utils.maintenance_schedule import project_schedule

TASK = "Property Maintenance Task"
DEFAULT_LEAD_DAYS = 3
BACKFILL_DAYS = 31


def lead_days():
    value = frappe.db.get_single_value("Property Core Settings", "maintenance_task_lead_days")
    return DEFAULT_LEAD_DAYS if value in (None, "") else max(cint(value), 0)


def generate_for_unit(property_unit, today_date=None):
    """Tasks due on this unit within the lead window. Returns the new names."""
    today_date = getdate(today_date or today())
    horizon = getdate(add_days(today_date, lead_days()))
    oldest = getdate(add_days(today_date, -BACKFILL_DAYS))

    unit = frappe.db.get_value(
        "Property Unit", property_unit,
        ["name", "unit_number", "customer", "maintenance_plan_template", "pause_maintenance"],
        as_dict=True,
    )
    if not unit or not unit.maintenance_plan_template or unit.pause_maintenance or not unit.customer:
        return []

    assignee = frappe.db.get_single_value("Property Core Settings", "maintenance_task_assignee")
    created = []
    for row in project_schedule(property_unit, months_ahead=2):
        due = getdate(row["due_date"])
        if due > horizon or due < oldest or row["status"] == "Paused":
            continue
        if frappe.db.exists(TASK, {"property_unit": property_unit, "maintenance_period": row["period"]}):
            continue
        doc = frappe.get_doc(
            {
                "doctype": TASK,
                "subject": _("Maintenance {0} - {1}").format(row["period"], unit.unit_number or unit.name),
                "property_unit": property_unit,
                "source": "Schedule",
                "maintenance_plan_template": unit.maintenance_plan_template,
                "maintenance_period": row["period"],
                "scheduled_date": due,
                "charge_amount": row["amount"],
                "sales_invoice": row.get("invoice"),
                "description": row.get("description"),
                "assigned_to": assignee or None,
                "status": "Open",
            }
        )
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        created.append(doc.name)
    return created


def link_invoice(property_unit, period, invoice):
    """The charge for a period was raised: tie it to that period's task."""
    task = frappe.db.get_value(TASK, {"property_unit": property_unit, "maintenance_period": period}, "name")
    if task:
        frappe.db.set_value(TASK, task, "sales_invoice", invoice, update_modified=False)


def run_daily():
    units = frappe.get_all(
        "Property Unit",
        filters={
            "pause_maintenance": 0,
            "maintenance_plan_template": ["is", "set"],
            "maintenance_start_date": ["is", "set"],
            "customer": ["is", "set"],
        },
        pluck="name",
    )
    for unit in units:
        try:
            generate_for_unit(unit)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Maintenance Task: {unit}")
    frappe.db.commit()


@frappe.whitelist()
def generate_now(property_unit):
    frappe.has_permission("Property Unit", "write", doc=property_unit, throw=True)
    return {"created": generate_for_unit(property_unit)}
