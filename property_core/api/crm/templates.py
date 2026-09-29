"""The two templates a unit carries, and the charges they raise.

* **Payment Plan Template** -- how the sale price is split into milestones
  (``percentage`` of the agreed value, due ``offset_months`` after booking).
  Picked on the property, overridden on a unit, overridden again on a booking.
* **Maintenance Plan Template** -- the recurring charges after possession:
  a fixed schedule of one-off rows (``month_no`` after the start, amount)
  plus a repeating charge every ``repeat_every_n_months``.

Admin-only to write (the doctypes grant Property Manager); everyone reads.
"""

import frappe
from frappe import _
from frappe.utils import add_months, flt, today

from property_core.api.crm import base
from property_core.api.utils import ok

PAYMENT = "Payment Plan Template"
MAINTENANCE = "Maintenance Plan Template"


# --------------------------------------------------------------------------- #
# payment plan templates
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_payment_templates():
    base.require_user()
    out = []
    for name in frappe.get_list(PAYMENT, pluck="name", order_by="name asc"):
        out.append(_payment_payload(frappe.get_doc(PAYMENT, name)))
    return ok(data=out)


@frappe.whitelist()
def get_payment_template(name):
    return ok(data=_payment_payload(base.read_doc(PAYMENT, name)))


@frappe.whitelist()
def save_payment_template(template_name, milestones, name=None):
    """Create (no ``name``) or replace. ``milestones``:
    ``[{"milestone": "Booking", "percentage": 10, "offset_months": 0}, …]`` --
    percentages must add up to 100."""
    base.require_user()
    rows = base.parse(milestones, default=[]) or []
    _check_milestones(rows)

    if name:
        doc = base.read_doc(PAYMENT, name)
        doc.check_permission("write")
        doc.set("milestones", [])
    else:
        doc = frappe.new_doc(PAYMENT)
        doc.template_name = template_name
    for row in rows:
        doc.append(
            "milestones",
            {
                "milestone": row.get("milestone"),
                "percentage": flt(row.get("percentage")),
                "offset_months": int(row.get("offset_months") or 0),
            },
        )
    doc.save() if name else doc.insert()
    if name and template_name and template_name != doc.name:
        frappe.rename_doc(PAYMENT, doc.name, template_name)
        doc = frappe.get_doc(PAYMENT, template_name)
    return ok(data=_payment_payload(doc), message=_("Template {0} saved").format(doc.name))


@frappe.whitelist()
def delete_payment_template(name):
    doc = base.read_doc(PAYMENT, name)
    doc.check_permission("delete")
    frappe.delete_doc(PAYMENT, name)
    return ok(data={"name": name}, message=_("Template deleted"))


@frappe.whitelist()
def preview_payment_plan(amount=None, template=None, property_unit=None, booking_date=None):
    """What the plan would look like for this price, before anybody books --
    the schedule a salesperson shows the customer. With only
    ``property_unit`` the unit's (or its property's) template and base price
    are used."""
    base.require_user()
    from property_core.property_core.utils.allocation_engine import DEFAULT_MILESTONES

    if not template and property_unit:
        unit = frappe.db.get_value(
            "Property Unit", property_unit, ["payment_plan_template", "property", "base_price"], as_dict=True
        )
        if unit:
            template = unit.payment_plan_template or frappe.db.get_value(
                "Property", unit.property, "payment_plan_template"
            )
            amount = amount or unit.base_price
    amount = flt(amount)
    start = booking_date or today()
    rows = (
        [r.as_dict() for r in frappe.get_doc(PAYMENT, template).milestones] if template else DEFAULT_MILESTONES
    )
    schedule = [
        {
            "milestone": r["milestone"],
            "percentage": flt(r["percentage"]),
            "due_date": str(add_months(start, int(r["offset_months"] or 0))),
            "amount": flt(amount * flt(r["percentage"]) / 100, 2),
        }
        for r in rows
    ]
    return ok(data={"template": template, "amount": amount, "schedule": schedule})


def _check_milestones(rows):
    if not rows:
        frappe.throw(_("Add at least one milestone"), frappe.MandatoryError)
    total = sum(flt(r.get("percentage")) for r in rows)
    if abs(total - 100) > 0.01:
        frappe.throw(_("Milestone percentages add up to {0}, not 100").format(total))
    for r in rows:
        if not r.get("milestone"):
            frappe.throw(_("Every milestone needs a name"))


def _payment_payload(doc):
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "milestones": [
            {"milestone": r.milestone, "percentage": flt(r.percentage), "offset_months": r.offset_months}
            for r in doc.milestones
        ],
        "used_by": {
            "properties": frappe.db.count("Property", {"payment_plan_template": doc.name}),
            "units": frappe.db.count("Property Unit", {"payment_plan_template": doc.name}),
        },
    }


# --------------------------------------------------------------------------- #
# maintenance (recurring charges) templates
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_maintenance_templates(include_disabled=0):
    base.require_user()
    if not frappe.db.exists("DocType", MAINTENANCE):
        return ok(data=[])
    filters = {} if base.as_bool(include_disabled) else {"disabled": 0}
    return ok(
        data=[
            _maintenance_payload(frappe.get_doc(MAINTENANCE, n))
            for n in frappe.get_list(MAINTENANCE, filters=filters, pluck="name", order_by="name asc")
        ]
    )


@frappe.whitelist()
def get_maintenance_template(name):
    return ok(data=_maintenance_payload(base.read_doc(MAINTENANCE, name)))


@frappe.whitelist()
def save_maintenance_template(
    template_name, schedule=None, repeat_every_n_months=0, repeat_amount=0, repeat_item_code=None, disabled=0, name=None
):
    """``schedule``: one-off charges,
    ``[{"month_no": 0, "description": "Corpus fund", "amount": 25000, "item_code": null, "fixed_due_date": null}]``.
    ``repeat_*``: the recurring charge (e.g. every 1 month, 2500)."""
    base.require_user()
    rows = base.parse(schedule, default=[]) or []
    if name:
        doc = base.read_doc(MAINTENANCE, name)
        doc.check_permission("write")
        doc.set("schedule", [])
    else:
        doc = frappe.new_doc(MAINTENANCE)
        doc.template_name = template_name
    doc.repeat_every_n_months = int(repeat_every_n_months or 0)
    doc.repeat_amount = flt(repeat_amount)
    doc.repeat_item_code = repeat_item_code or None
    doc.disabled = 1 if base.as_bool(disabled) else 0
    for row in rows:
        doc.append(
            "schedule",
            {
                "month_no": int(row.get("month_no") or 0),
                "description": row.get("description"),
                "amount": flt(row.get("amount")),
                "fixed_due_date": row.get("fixed_due_date"),
                "item_code": row.get("item_code"),
            },
        )
    doc.save() if name else doc.insert()
    return ok(data=_maintenance_payload(doc), message=_("Template {0} saved").format(doc.name))


def _maintenance_payload(doc):
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "disabled": doc.disabled,
        "repeat_every_n_months": doc.repeat_every_n_months,
        "repeat_amount": flt(doc.repeat_amount),
        "repeat_item_code": doc.repeat_item_code,
        "schedule": [
            {
                "month_no": r.month_no,
                "description": r.description,
                "amount": flt(r.amount),
                "fixed_due_date": str(r.fixed_due_date) if r.fixed_due_date else None,
                "item_code": r.item_code,
            }
            for r in doc.schedule
        ],
        "used_by_units": frappe.db.count("Property Unit", {"maintenance_plan_template": doc.name})
        if frappe.get_meta("Property Unit").has_field("maintenance_plan_template")
        else 0,
    }


# --------------------------------------------------------------------------- #
# putting templates on units
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def apply_templates(
    units=None, property=None, payment_plan_template=None, maintenance_plan_template=None, maintenance_start_date=None, only_available=0
):
    """Set the payment plan and/or maintenance template on many units at once:
    a JSON list of ``units``, or every unit of ``property``. Pass ``""`` to
    clear a template; leave it out (null) to not touch it."""
    base.require_user()
    if not frappe.has_permission("Property Unit", "write"):
        frappe.throw(_("Not permitted to change units"), frappe.PermissionError)

    names = base.parse(units, default=[]) or []
    if property:
        filters = {"property": property}
        if base.as_bool(only_available):
            filters["availability_status"] = "Available"
        names += frappe.get_list("Property Unit", filters=filters, pluck="name")
    if not names:
        frappe.throw(_("No units given"), frappe.MandatoryError)

    values = {}
    if payment_plan_template is not None:
        values["payment_plan_template"] = payment_plan_template or None
    has_maintenance = frappe.get_meta("Property Unit").has_field("maintenance_plan_template")
    if has_maintenance and maintenance_plan_template is not None:
        values["maintenance_plan_template"] = maintenance_plan_template or None
    if has_maintenance and maintenance_start_date is not None:
        values["maintenance_start_date"] = maintenance_start_date or None
    if not values:
        frappe.throw(_("Nothing to apply"))

    updated = []
    for name in dict.fromkeys(names):
        doc = base.read_doc("Property Unit", name)
        doc.check_permission("write")
        doc.update(values)
        doc.save()
        updated.append(name)
    return ok(data={"updated": updated, "values": values}, message=_("{0} unit(s) updated").format(len(updated)))
