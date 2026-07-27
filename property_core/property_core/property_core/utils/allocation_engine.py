import frappe
from frappe.utils import add_months, today


DEFAULT_MILESTONES = [
    {"milestone": "Booking Amount", "offset_months": 0, "percentage": 10},
    {"milestone": "On Agreement", "offset_months": 1, "percentage": 20},
    {"milestone": "On Foundation", "offset_months": 3, "percentage": 20},
    {"milestone": "On Structure", "offset_months": 6, "percentage": 25},
    {"milestone": "On Possession", "offset_months": 12, "percentage": 25},
]


def _get_milestones(booking_doc):
    unit = frappe.get_doc("Property Unit", booking_doc.property_unit)
    template_name = frappe.db.get_value("Property", unit.property, "payment_plan_template")

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
    unit = frappe.get_doc("Property Unit", booking_doc.property_unit)
    total_price = unit.base_price or 0

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
