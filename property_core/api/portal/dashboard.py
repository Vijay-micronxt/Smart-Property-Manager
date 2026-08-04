"""One call that fills a portal home screen."""

import frappe
from frappe.utils import flt

from property_core.api.portal.base import customer_units, get_customer, get_list, serialize
from property_core.api.portal.billing import charges
from property_core.api.portal.bookings import _decorate as decorate_booking
from property_core.api.utils import ok


@frappe.whitelist()
def summary(recent_limit=5):
    """Headline numbers plus the few rows a landing screen shows.

    Deliberately shallow -- every section has a dedicated endpoint that returns
    the full list when the customer opens that tab.
    """
    customer = get_customer()
    recent_limit = int(recent_limit)

    units = customer_units(customer)
    charge_data = charges(limit=500)["data"]

    outstanding_rows = [
        row for row in charge_data["charges"] if flt(row["outstanding"]) > 0
    ]
    outstanding_rows.sort(key=lambda r: (r.get("due_date") or "9999-12-31"))
    next_due = outstanding_rows[0] if outstanding_rows else None

    bookings = get_list(
        "Property Booking",
        {"customer": customer, "docstatus": ["<", 2]},
        order_by="creation desc", limit_page_length=recent_limit,
    )
    for booking in bookings:
        decorate_booking(booking)

    open_issues = get_list(
        "Issue",
        {"customer": customer, "status": ["not in", ["Closed", "Resolved"]]},
        order_by="creation desc", limit_page_length=recent_limit,
    )

    recent_payments = get_list(
        "Payment Entry",
        {"party_type": "Customer", "party": customer, "docstatus": 1},
        order_by="posting_date desc", limit_page_length=recent_limit,
    )

    recent_work = []
    if units:
        recent_work = get_list(
            "Work Order",
            {"property_unit": ["in", units]},
            order_by="coalesce(completed_date, scheduled_date, creation) desc",
            limit_page_length=recent_limit,
        )

    return ok(data=serialize({
        "customer": {
            "name": customer,
            "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
        },
        "totals": {
            "units": len(units),
            "bookings": frappe.db.count("Property Booking", {"customer": customer, "docstatus": ["<", 2]}),
            "outstanding": charge_data["totals"]["outstanding"],
            "overdue": charge_data["totals"]["overdue"],
            "paid": sum(flt(p.get("paid_amount")) for p in recent_payments),
            "open_issues": frappe.db.count(
                "Issue", {"customer": customer, "status": ["not in", ["Closed", "Resolved"]]}
            ),
            "open_work_orders": frappe.db.count(
                "Work Order", {"property_unit": ["in", units], "status": ["!=", "Completed"]}
            ) if units else 0,
        },
        "by_charge_type": charge_data["by_type"],
        "next_due": next_due,
        "recent_bookings": bookings,
        "recent_payments": recent_payments,
        "recent_work_orders": recent_work,
        "open_issues": open_issues,
    }))
