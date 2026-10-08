import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate


class CommissionEntry(Document):
    pass


def create_commission_entry(doc, method=None):
    """Hook: auto-create Commission Entry when a Property Booking is submitted.

    A percentage rule applies to the agreement value by default (Property Core
    Settings -> Commission Calculated On): a broker's 2% is 2% of the deal, not
    of the token the customer put down.
    """
    if not doc.sales_person:
        return

    rule = _find_commission_rule(doc)
    if not rule:
        return

    from property_core.property_core.utils import settings

    if settings.get("commission_base") == "Booking Amount":
        base_amount = flt(doc.booking_amount)
    else:
        base_amount = flt(doc.total_price)

    if rule.commission_type == "Percentage":
        amount = base_amount * flt(rule.commission_rate) / 100
    else:
        amount = flt(rule.commission_rate)

    entry = frappe.new_doc("Commission Entry")
    entry.booking = doc.name
    entry.sales_person = doc.sales_person
    entry.property_unit = doc.property_unit
    entry.customer = doc.customer
    entry.commission_date = doc.booking_date
    entry.booking_amount = doc.booking_amount
    entry.base_amount = base_amount
    entry.commission_type = rule.commission_type
    entry.commission_rate = rule.commission_rate
    entry.commission_amount = flt(amount, 2)
    entry.commission_rule = rule.name
    entry.status = "Pending"
    entry.insert(ignore_permissions=True)

    refresh_for_booking(doc.name)


def cancel_commission_entry(doc, method=None):
    """Hook: a cancelled booking earns nothing more; commission already paid on
    it is to be recovered (status Clawback, negative Payable Now) through the
    sales person's next settlement."""
    refresh_for_booking(doc.name)


def refresh_for_booking(booking):
    """Recompute how much of each entry on the booking is payable.

    Called on booking submit / cancel and whenever the booking's collections
    change (property_booking_collection_changed hook)."""
    entries = frappe.get_all(
        "Commission Entry",
        filters={"booking": booking, "status": ["!=", "Cancelled"]},
        fields=["name", "commission_amount", "commission_rule", "settled_amount"],
    )
    if not entries:
        return

    docstatus, total_price = frappe.db.get_value("Property Booking", booking, ["docstatus", "total_price"])
    paid = sum(
        flt(r) for r in frappe.get_all("Payment Plan", filters={"booking": booking}, pluck="paid_amount")
    )
    paid_percent = flt(paid * 100 / flt(total_price), 4) if flt(total_price) else 0

    for e in entries:
        amount = flt(e.commission_amount)
        settled = flt(e.settled_amount)
        if docstatus == 2:
            released = 0
        else:
            released = flt(amount * _release_percent(e.commission_rule, paid_percent) / 100, 2)
        payable = flt(released - settled, 2)

        if docstatus == 2:
            status = "Clawback" if settled > 0.005 else "Cancelled"
        elif settled >= amount - 0.005 and amount > 0:
            status = "Settled"
        elif settled > 0.005:
            status = "Partly Settled"
        else:
            status = "Pending"

        frappe.db.set_value(
            "Commission Entry", e.name,
            {
                "customer_paid_percent": min(paid_percent, 100),
                "released_amount": released,
                "payable_amount": payable,
                "status": status,
            },
            update_modified=False,
        )


def _release_percent(rule, paid_percent):
    stages = frappe.get_all(
        "Commission Release Stage",
        filters={"parent": rule, "parenttype": "Commission Rule"},
        fields=["customer_paid_percent", "release_percent"],
        order_by="customer_paid_percent asc",
    ) if rule else []
    if not stages:
        return 100
    released = 0
    for stage in stages:
        if paid_percent + 0.0001 >= flt(stage.customer_paid_percent):
            released = flt(stage.release_percent)
    return released


def _find_commission_rule(booking):
    """Return the highest-priority active Commission Rule for this booking."""
    today = getdate(booking.booking_date)
    fields = ["name", "commission_type", "commission_rate", "effective_from", "effective_to"]

    def is_effective(row):
        if row.effective_from and getdate(row.effective_from) > today:
            return False
        if row.effective_to and getdate(row.effective_to) < today:
            return False
        return True

    def first_effective(rules):
        for row in rules:
            if is_effective(row):
                return row
        return None

    def base_filters():
        return [
            ["is_active", "=", 1],
            ["commission_rate", ">", 0],
        ]

    property_name = frappe.db.get_value("Property Unit", booking.property_unit, "property")

    # Priority 1: specific property + specific sales_person
    if property_name and booking.sales_person:
        rules = frappe.get_all(
            "Commission Rule",
            filters=base_filters() + [
                ["property", "=", property_name],
                ["sales_person", "=", booking.sales_person],
            ],
            fields=fields,
        )
        rule = first_effective(rules)
        if rule:
            return rule

    # Priority 2: specific property only
    if property_name:
        rules = frappe.get_all(
            "Commission Rule",
            filters=base_filters() + [
                ["property", "=", property_name],
                ["sales_person", "in", ["", None]],
            ],
            fields=fields,
        )
        rule = first_effective(rules)
        if rule:
            return rule

    # Priority 3: specific sales_person only
    if booking.sales_person:
        rules = frappe.get_all(
            "Commission Rule",
            filters=base_filters() + [
                ["property", "in", ["", None]],
                ["sales_person", "=", booking.sales_person],
            ],
            fields=fields,
        )
        rule = first_effective(rules)
        if rule:
            return rule

    # Priority 4: global rule (no property, no sales_person)
    rules = frappe.get_all(
        "Commission Rule",
        filters=base_filters() + [
            ["property", "in", ["", None]],
            ["sales_person", "in", ["", None]],
        ],
        fields=fields,
    )
    return first_effective(rules)
