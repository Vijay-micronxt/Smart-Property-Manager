import frappe
from frappe.utils import add_months, today


DEFAULT_MILESTONES = [
    {"milestone": "Booking Amount", "offset_months": 0, "percentage": 10},
    {"milestone": "On Agreement", "offset_months": 1, "percentage": 20},
    {"milestone": "On Foundation", "offset_months": 3, "percentage": 20},
    {"milestone": "On Structure", "offset_months": 6, "percentage": 25},
    {"milestone": "On Possession", "offset_months": 12, "percentage": 25},
]


def resolve_template(booking_doc):
    """Booking beats unit beats property. A villa and a plot in the same
    township rarely share a payment schedule, and a negotiated deal can differ
    from both."""
    if booking_doc.get("payment_plan_template"):
        return booking_doc.payment_plan_template

    unit = frappe.db.get_value(
        "Property Unit",
        booking_doc.property_unit,
        ["payment_plan_template", "property"],
        as_dict=True,
    )
    if not unit:
        return None
    if unit.payment_plan_template:
        return unit.payment_plan_template

    return frappe.db.get_value("Property", unit.property, "payment_plan_template")


def resolve_total_price(booking_doc):
    """The agreed value drives the plan, not the list price."""
    if booking_doc.get("total_price"):
        return booking_doc.total_price
    return frappe.db.get_value("Property Unit", booking_doc.property_unit, "base_price") or 0


def _get_milestones(booking_doc):
    template_name = resolve_template(booking_doc)

    if template_name:
        template = frappe.get_doc("Payment Plan Template", template_name)
        return [
            {
                "milestone": row.milestone,
                "offset_months": row.offset_months,
                "percentage": row.percentage,
            }
            for row in template.milestones
        ]

    return DEFAULT_MILESTONES


def generate_payment_plan(booking_doc):
    total_price = resolve_total_price(booking_doc)

    if not total_price:
        return

    existing = frappe.db.exists("Payment Plan", {"booking": booking_doc.name})
    if existing:
        return

    base_date = booking_doc.booking_date or today()
    milestones = _get_milestones(booking_doc)

    for item in milestones:
        pp = frappe.new_doc("Payment Plan")
        pp.booking = booking_doc.name
        pp.milestone = item["milestone"]
        pp.due_date = add_months(base_date, item["offset_months"])
        pp.amount = round(total_price * item["percentage"] / 100, 2)
        pp.payment_status = "Pending"
        pp.insert(ignore_permissions=True)
