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

    def base_filters():
        return [
            ["is_active", "=", 1],
            ["commission_rate", ">", 0],
            [
                "ifnull(effective_from, '2000-01-01')", "<=", today
            ],
            [
                "ifnull(effective_to, '2099-12-31')", ">=", today
            ],
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
            fields=["name", "commission_type", "commission_rate"],
            limit=1,
        )
        if rules:
            return rules[0]

    # Priority 2: specific property only
    if property_name:
        rules = frappe.get_all(
            "Commission Rule",
            filters=base_filters() + [
                ["property", "=", property_name],
                ["sales_person", "in", ["", None]],
            ],
            fields=["name", "commission_type", "commission_rate"],
            limit=1,
        )
        if rules:
            return rules[0]

    # Priority 3: specific sales_person only
    if booking.sales_person:
        rules = frappe.get_all(
            "Commission Rule",
            filters=base_filters() + [
                ["property", "in", ["", None]],
                ["sales_person", "=", booking.sales_person],
            ],
            fields=["name", "commission_type", "commission_rate"],
            limit=1,
        )
        if rules:
            return rules[0]

    # Priority 4: global rule (no property, no sales_person)
    rules = frappe.get_all(
        "Commission Rule",
        filters=base_filters() + [
            ["property", "in", ["", None]],
            ["sales_person", "in", ["", None]],
        ],
        fields=["name", "commission_type", "commission_rate"],
        limit=1,
    )
    return rules[0] if rules else None
