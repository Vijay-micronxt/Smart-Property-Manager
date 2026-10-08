import frappe
from frappe import _
from frappe.utils import add_months, flt, getdate, today


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


def build_schedule(total_price, milestones, base_date, booking_amount=0, advance_first=True):
    """The instalments for an agreement, as plain rows.

    With ``advance_first`` and a booking amount, that amount is the first
    instalment, due on the booking date, and it counts toward the template's
    milestones in order -- the earliest ones shrink (and drop out once fully
    covered) so the plan still adds up to the agreement value. A template whose
    first milestone is "10% on booking" and a booking amount of exactly that 10%
    gives the template unchanged; a smaller token leaves the balance of that
    milestone on its own due date.
    """
    total_price = flt(total_price)
    rows = [
        {
            "milestone": m["milestone"],
            "due_date": add_months(base_date, int(m.get("offset_months") or 0)),
            "percentage": flt(m.get("percentage")),
            "amount": flt(total_price * flt(m.get("percentage")) / 100, 2),
        }
        for m in milestones
    ]

    # percentages that add up to 100 must bill the agreement value to the paisa
    if rows and abs(sum(r["percentage"] for r in rows) - 100) < 0.001:
        rows[-1]["amount"] = flt(rows[-1]["amount"] + total_price - sum(r["amount"] for r in rows), 2)

    advance = min(flt(booking_amount), total_price)
    if not (advance_first and advance > 0):
        return rows

    left = advance
    for row in rows:
        if left <= 0:
            break
        take = min(left, row["amount"])
        row["amount"] = flt(row["amount"] - take, 2)
        left = flt(left - take, 2)
        if row["amount"] > 0:
            row["milestone"] = _("{0} (balance)").format(row["milestone"])

    rows = [r for r in rows if r["amount"] > 0.005]
    rows.insert(0, {
        "milestone": _("Booking Amount"),
        "due_date": getdate(base_date),
        "percentage": flt(advance * 100 / total_price, 4) if total_price else 0,
        "amount": advance,
    })
    return rows


def generate_payment_plan(booking_doc):
    total_price = resolve_total_price(booking_doc)

    if not total_price:
        return

    existing = frappe.db.exists("Payment Plan", {"booking": booking_doc.name})
    if existing:
        return

    from property_core.property_core.utils import settings

    rows = build_schedule(
        total_price,
        _get_milestones(booking_doc),
        booking_doc.booking_date or today(),
        booking_amount=booking_doc.get("booking_amount"),
        advance_first=settings.get("booking_amount_first_instalment"),
    )

    for row in rows:
        pp = frappe.new_doc("Payment Plan")
        pp.booking = booking_doc.name
        pp.milestone = row["milestone"]
        pp.due_date = row["due_date"]
        pp.amount = row["amount"]
        pp.payment_status = "Pending"
        pp.outstanding_amount = pp.amount
        pp.insert(ignore_permissions=True)


def invoice_due_instalments(booking_name):
    """Bill what is already due -- the booking amount on the booking date --
    now, rather than at the next nightly run. The customer is usually standing
    at the counter with the cheque."""
    names = frappe.get_all(
        "Payment Plan",
        filters={
            "booking": booking_name,
            "payment_status": "Pending",
            "invoice": ["is", "not set"],
            "due_date": ["<=", today()],
        },
        pluck="name",
        order_by="due_date asc",
    )
    for name in names:
        try:
            frappe.get_doc("Payment Plan", name).generate_invoice()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Instalment invoice on booking failed: {name}")
