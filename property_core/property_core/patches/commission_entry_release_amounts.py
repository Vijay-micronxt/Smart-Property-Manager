"""Fill base / settled / payable on existing Commission Entries.

Entries made before release stages were paid as a whole: Settled ones are
fully settled, the rest nothing yet. Their base was the booking amount.
"""

import frappe
from frappe.utils import flt


def execute():
    from property_core.property_commissions.doctype.commission_entry.commission_entry import refresh_for_booking

    bookings = set()
    for e in frappe.get_all(
        "Commission Entry",
        fields=["name", "booking", "status", "commission_amount", "booking_amount", "base_amount"],
    ):
        frappe.db.set_value(
            "Commission Entry", e.name,
            {
                "base_amount": e.base_amount or flt(e.booking_amount),
                "settled_amount": flt(e.commission_amount) if e.status == "Settled" else 0,
            },
            update_modified=False,
        )
        bookings.add(e.booking)
    for booking in filter(None, bookings):
        refresh_for_booking(booking)
