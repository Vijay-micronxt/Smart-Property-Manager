"""Bookings the customer holds, and the portal booking request flow."""

import frappe
from frappe.utils import today

from property_core.api.portal.base import (
    assert_doc,
    due_status,
    get_customer,
    get_list,
    serialize,
)
from property_core.api.utils import ok


def _schedule_for(booking_name):
    """Payment Plan milestones with a computed due status."""
    rows = get_list("Payment Plan", {"booking": booking_name}, order_by="due_date asc")
    for row in rows:
        paid = row.get("payment_status") == "Paid"
        row["status"] = "Paid" if paid else due_status(row.get("due_date"), 1)
        if row.get("invoice"):
            row["invoice_details"] = serialize(frappe.db.get_value(
                "Sales Invoice", row["invoice"],
                ["grand_total", "outstanding_amount", "status", "due_date"],
                as_dict=True,
            ))
    return rows


def _decorate(booking):
    booking["payment_plan"] = _schedule_for(booking["name"])
    booking["paid_amount"] = sum(
        float(p.get("amount") or 0) for p in booking["payment_plan"] if p.get("status") == "Paid"
    )
    booking["outstanding"] = float(booking.get("booking_amount") or 0) - booking["paid_amount"]
    booking["confirmed"] = 1 if booking.get("docstatus") == 1 else 0
    if booking.get("property_unit"):
        unit = frappe.db.get_value(
            "Property Unit", booking["property_unit"],
            ["unit_number", "property", "project"], as_dict=True,
        ) or {}
        booking["unit_number"] = unit.get("unit_number")
        # older bookings were saved before these fetch fields existed
        booking["unit_property"] = booking.get("unit_property") or unit.get("property")
        booking["project"] = booking.get("project") or unit.get("project")
    if booking.get("unit_property"):
        booking["property_name"] = frappe.db.get_value(
            "Property", booking["unit_property"], "property_name"
        )
    return booking


@frappe.whitelist()
def list_bookings(status=None, limit=50):
    customer = get_customer()

    filters = {"customer": customer, "docstatus": ["<", 2]}
    if status:
        filters["booking_status"] = status

    rows = get_list(
        "Property Booking", filters, order_by="creation desc", limit_page_length=int(limit)
    )
    for row in rows:
        _decorate(row)

    return ok(data={"bookings": rows, "total": len(rows)})


@frappe.whitelist()
def booking_details(booking):
    customer = get_customer()
    assert_doc(customer, "Property Booking", booking)

    rows = get_list("Property Booking", {"name": booking})
    if not rows:
        frappe.throw(frappe._("Booking not found"))
    row = _decorate(rows[0])

    row["agreements"] = get_list(
        "Property Agreement",
        {"property_unit": row.get("property_unit"), "customer": customer},
        order_by="creation desc",
    )
    row["allocations"] = get_list(
        "Property Allocation",
        {"booking": booking, "docstatus": ["<", 2]},
        order_by="creation desc",
    )

    return ok(data=row)


@frappe.whitelist()
def book_unit(property_unit, note=None):
    """Portal booking request -- creates a DRAFT Property Booking for staff to
    verify and submit. Pricing comes from the unit; the client cannot set it."""
    customer = get_customer()

    unit = frappe.db.get_value(
        "Property Unit", property_unit,
        ["name", "property", "unit_number", "availability_status", "base_price"],
        as_dict=True,
    )
    if not unit:
        frappe.throw(frappe._("Unit not found"))
    if unit.availability_status != "Available":
        frappe.throw(frappe._("Unit {0} is not available").format(unit.unit_number))

    active = frappe.db.exists(
        "Property Booking",
        {
            "property_unit": property_unit,
            "docstatus": ["<", 2],
            "booking_status": ["!=", "Cancelled"],
        },
    )
    if active:
        frappe.throw(frappe._("Unit {0} already has an active booking").format(unit.unit_number))

    booking = frappe.get_doc({
        "doctype": "Property Booking",
        "customer": customer,
        "property_unit": property_unit,
        "booking_date": today(),
        "booking_status": "Draft",
        "booking_amount": unit.base_price or 0,
        "notes": "Requested via customer portal."
                 + (" Customer note: " + note.strip() if note and note.strip() else ""),
    })
    booking.insert(ignore_permissions=True)

    _notify_managers(
        booking.name,
        frappe._("Portal booking request: {0} for unit {1} by {2}. Verify and submit.").format(
            booking.name, unit.unit_number, customer
        ),
    )

    return ok(
        message=frappe._("Booking request received. Our team will confirm shortly."),
        data={
            "booking": booking.name,
            "unit": unit.unit_number,
            "property_unit": property_unit,
            "status": "pending_confirmation",
        },
    )


def _notify_managers(booking_name, description):
    managers = frappe.get_all(
        "Has Role",
        filters={"role": "Property Manager", "parenttype": "User"},
        pluck="parent",
        limit=10,
    )
    for user in managers:
        if not frappe.db.get_value("User", user, "enabled"):
            continue
        frappe.get_doc({
            "doctype": "ToDo",
            "allocated_to": user,
            "reference_type": "Property Booking",
            "reference_name": booking_name,
            "description": description,
            "priority": "High",
        }).insert(ignore_permissions=True)
