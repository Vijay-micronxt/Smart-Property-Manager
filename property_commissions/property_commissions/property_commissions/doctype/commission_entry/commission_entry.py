import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class CommissionEntry(Document):
    pass


def create_commission_entry(doc, method=None):
    """Hook: auto-create Commission Entry when a Property Booking is submitted."""
    if not doc.sales_person:
        return

    rule = _find_commission_rule(doc)
    if not rule:
        return

    if rule.commission_type == "Percentage":
        amount = (doc.booking_amount or 0) * rule.commission_rate / 100
    else:
        amount = rule.commission_rate

    entry = frappe.new_doc("Commission Entry")
    entry.booking = doc.name
    entry.sales_person = doc.sales_person
    entry.property_unit = doc.property_unit
    entry.customer = doc.customer
    entry.commission_date = doc.booking_date
    entry.booking_amount = doc.booking_amount
    entry.commission_type = rule.commission_type
    entry.commission_rate = rule.commission_rate
    entry.commission_amount = amount
    entry.commission_rule = rule.name
    entry.status = "Pending"
    entry.insert(ignore_permissions=True)


def cancel_commission_entry(doc, method=None):
    """Hook: cancel Commission Entry when a Property Booking is cancelled."""
    entries = frappe.get_all(
        "Commission Entry",
        filters={"booking": doc.name, "status": "Pending"},
        fields=["name"],
    )
    for e in entries:
        frappe.db.set_value("Commission Entry", e.name, "status", "Cancelled", update_modified=False)


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
