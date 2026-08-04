"""
Everything money: charges the customer owes, and what they have paid.

``charges()`` is the one endpoint a portal "Payments" tab needs -- it merges
booking milestones, recurring maintenance, utility bills and rent into a single
type-tagged feed. The narrower endpoints below stay available for tabs that
want one stream on its own.
"""

import frappe
from frappe.utils import flt

from property_core.api.portal.base import (
    as_int,
    assert_doc,
    assert_unit,
    child_rows,
    due_status,
    get_customer,
    get_list,
    serialize,
)
from property_core.api.utils import ok

CHARGE_TYPES = ("Booking Milestone", "Maintenance", "Utility", "Rent", "Other")


# ─── Unified feed ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def charges(property_unit=None, charge_type=None, status=None, limit=200):
    """Every charge raised against the customer, newest due date first.

    Each row carries ``charge_type`` (see ``CHARGE_TYPES``), ``amount``,
    ``outstanding``, ``due_date`` and a computed ``status``, so a client can
    render one table without knowing which doctype it came from.
    """
    customer = get_customer()
    limit = as_int(limit, 200)

    rows = []
    rows += _milestone_charges(customer, property_unit)
    rows += _invoice_charges(customer, property_unit)
    rows += _utility_charges(customer, property_unit)

    if charge_type:
        rows = [r for r in rows if r["charge_type"] == charge_type]
    if status:
        rows = [r for r in rows if r["status"] == status]

    rows.sort(key=lambda r: (r.get("due_date") or "", r.get("reference") or ""), reverse=True)
    rows = rows[:limit]

    totals = {
        "total": sum(flt(r["amount"]) for r in rows),
        "outstanding": sum(flt(r["outstanding"]) for r in rows),
        "overdue": sum(flt(r["outstanding"]) for r in rows if r["status"] == "Overdue"),
        "paid": sum(flt(r["amount"]) for r in rows if r["status"] == "Paid"),
    }
    by_type = {}
    for row in rows:
        bucket = by_type.setdefault(row["charge_type"], {"count": 0, "amount": 0.0, "outstanding": 0.0})
        bucket["count"] += 1
        bucket["amount"] += flt(row["amount"])
        bucket["outstanding"] += flt(row["outstanding"])

    return ok(data={
        "charges": rows,
        "totals": totals,
        "by_type": by_type,
        "count": len(rows),
    })


def _milestone_charges(customer, property_unit=None):
    """Payment Plan milestones on the customer's bookings."""
    filters = {"customer": customer, "docstatus": ["<", 2]}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit

    bookings = frappe.get_all(
        "Property Booking", filters=filters, fields=["name", "property_unit"]
    )
    if not bookings:
        return []

    unit_by_booking = {b.name: b.property_unit for b in bookings}
    rows = get_list(
        "Payment Plan",
        {"booking": ["in", list(unit_by_booking)]},
        order_by="due_date asc",
    )

    out = []
    for row in rows:
        outstanding = 0 if row.get("payment_status") == "Paid" else flt(row.get("amount"))
        out.append({
            "charge_type": "Booking Milestone",
            "reference_doctype": "Payment Plan",
            "reference": row["name"],
            "property_unit": unit_by_booking.get(row.get("booking")),
            "booking": row.get("booking"),
            "description": row.get("milestone"),
            "period": None,
            "amount": flt(row.get("amount")),
            "outstanding": outstanding,
            "due_date": row.get("due_date"),
            "invoice": row.get("invoice"),
            "status": "Paid" if outstanding <= 0 else due_status(row.get("due_date"), outstanding),
        })
    return out


def _invoice_charges(customer, property_unit=None):
    """Submitted Sales Invoices -- maintenance, rent and anything else billed."""
    filters = {"customer": customer, "docstatus": 1}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit

    rows = get_list("Sales Invoice", filters, order_by="posting_date desc")

    rent_invoices = set()
    if frappe.db.exists("DocType", "Rent Invoice Log"):
        allocations = frappe.get_all(
            "Property Allocation",
            filters={"customer": customer, "docstatus": ["<", 2]},
            pluck="name",
        )
        if allocations:
            rent_invoices = set(
                frappe.get_all(
                    "Rent Invoice Log",
                    filters={"allocation": ["in", allocations], "invoice": ["is", "set"]},
                    pluck="invoice",
                )
            )

    out = []
    for row in rows:
        if row.get("maintenance_period"):
            charge_type = "Maintenance"
        elif row["name"] in rent_invoices:
            charge_type = "Rent"
        else:
            charge_type = "Other"

        out.append({
            "charge_type": charge_type,
            "reference_doctype": "Sales Invoice",
            "reference": row["name"],
            "property_unit": row.get("property_unit"),
            "booking": None,
            "description": row.get("remarks") or row.get("status"),
            "period": row.get("maintenance_period"),
            "amount": flt(row.get("grand_total")),
            "outstanding": flt(row.get("outstanding_amount")),
            "due_date": row.get("due_date") or row.get("posting_date"),
            "invoice": row["name"],
            "status": due_status(row.get("due_date"), row.get("outstanding_amount")),
        })
    return out


def _utility_charges(customer, property_unit=None):
    """Utility bills not yet turned into an invoice (invoiced ones arrive above)."""
    if not frappe.db.exists("DocType", "Utility Bill"):
        return []

    filters = {"customer": customer, "invoice": ["is", "not set"]}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit

    rows = get_list("Utility Bill", filters, order_by="billing_period_start desc")

    out = []
    for row in rows:
        paid = row.get("status") == "Paid"
        out.append({
            "charge_type": "Utility",
            "reference_doctype": "Utility Bill",
            "reference": row["name"],
            "property_unit": row.get("property_unit"),
            "booking": None,
            "description": frappe._("Utility usage {0} units").format(row.get("units_consumed") or 0),
            "period": row.get("billing_period_start"),
            "amount": flt(row.get("amount")),
            "outstanding": 0 if paid else flt(row.get("amount")),
            "due_date": row.get("billing_period_end"),
            "invoice": None,
            "status": "Paid" if paid else due_status(row.get("billing_period_end"), flt(row.get("amount"))),
        })
    return out


# ─── Individual streams ───────────────────────────────────────────────────────

@frappe.whitelist()
def maintenance_charges(property_unit=None, status=None, limit=60):
    """Recurring maintenance invoices, newest period first.

    These are the Sales Invoices raised by the daily maintenance billing job --
    identified by the ``maintenance_period`` field it stamps on them.
    """
    customer = get_customer()

    filters = {"customer": customer, "docstatus": 1, "maintenance_period": ["is", "set"]}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit

    rows = get_list(
        "Sales Invoice", filters,
        order_by="due_date desc", limit_page_length=as_int(limit, 60),
    )

    out = []
    for row in rows:
        row["status"] = due_status(row.get("due_date"), row.get("outstanding_amount"))
        row["period"] = row.get("maintenance_period")
        if row.get("property_unit"):
            row["unit_number"] = frappe.db.get_value(
                "Property Unit", row["property_unit"], "unit_number"
            )
        if status and row["status"] != status:
            continue
        out.append(row)

    return ok(data={
        "charges": out,
        "total_due": sum(flt(r.get("outstanding_amount")) for r in out),
        "total_billed": sum(flt(r.get("grand_total")) for r in out),
        "count": len(out),
    })


@frappe.whitelist()
def utility_bills(property_unit=None, status=None, limit=50):
    """Utility bills with the meter they were read from."""
    customer = get_customer()

    filters = {"customer": customer}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit
    if status:
        filters["status"] = status

    rows = get_list(
        "Utility Bill", filters,
        order_by="billing_period_start desc", limit_page_length=as_int(limit, 50),
    )
    for row in rows:
        meter = frappe.db.get_value(
            "Utility Meter", {"property_unit": row.get("property_unit")},
            ["meter_number", "utility_type", "unit_of_measure"], as_dict=True,
        )
        row["meter"] = meter or {}

    return ok(data={"bills": rows, "total": len(rows)})


@frappe.whitelist()
def rent_history(property_unit=None, limit=50):
    """Rent billing runs for the customer's allocations."""
    customer = get_customer()

    alloc_filters = {"customer": customer, "docstatus": ["<", 2]}
    if property_unit:
        assert_unit(customer, property_unit)
        alloc_filters["property_unit"] = property_unit

    allocations = frappe.get_all("Property Allocation", filters=alloc_filters, pluck="name")
    if not allocations:
        return ok(data={"rent_history": [], "total": 0})

    rows = get_list(
        "Rent Invoice Log", {"allocation": ["in", allocations]},
        order_by="period_start desc", limit_page_length=as_int(limit, 50),
    )
    for row in rows:
        if row.get("invoice"):
            row["invoice_details"] = serialize(frappe.db.get_value(
                "Sales Invoice", row["invoice"],
                ["grand_total", "outstanding_amount", "status", "due_date"], as_dict=True,
            ))

    return ok(data={"rent_history": rows, "total": len(rows)})


@frappe.whitelist()
def outstanding_dues():
    """Unpaid submitted invoices, oldest first, with running totals."""
    customer = get_customer()

    rows = get_list(
        "Sales Invoice",
        {"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
        order_by="due_date asc",
    )
    for row in rows:
        row["status"] = due_status(row.get("due_date"), row.get("outstanding_amount"))
        row["is_overdue"] = 1 if row["status"] == "Overdue" else 0

    return ok(data={
        "invoices": rows,
        "total_outstanding": sum(flt(r.get("outstanding_amount")) for r in rows),
        "total_overdue": sum(flt(r.get("outstanding_amount")) for r in rows if r["is_overdue"]),
        "invoice_count": len(rows),
    })


@frappe.whitelist()
def payments(limit=50):
    """Payments received from this customer, newest first, with what they settled."""
    customer = get_customer()

    rows = get_list(
        "Payment Entry",
        {"party_type": "Customer", "party": customer, "docstatus": 1},
        order_by="posting_date desc", limit_page_length=as_int(limit, 50),
    )
    for row in rows:
        row["allocated_to"] = get_list(
            "Payment Entry Reference",
            {"parent": row["name"], "reference_doctype": "Sales Invoice"},
            extra_fields=["reference_name", "allocated_amount"],
        )

    return ok(data={
        "payments": rows,
        "total_paid": sum(flt(r.get("paid_amount")) for r in rows),
        "count": len(rows),
    })


@frappe.whitelist()
def invoice(invoice):
    """One invoice in full: line items and the payments applied to it."""
    customer = get_customer()
    assert_doc(customer, "Sales Invoice", invoice)

    rows = get_list("Sales Invoice", {"name": invoice})
    row = rows[0]
    row["status"] = due_status(row.get("due_date"), row.get("outstanding_amount"))
    row["items"] = child_rows("Sales Invoice Item", invoice, parenttype="Sales Invoice")
    row["payments"] = get_list(
        "Payment Entry Reference",
        {"reference_doctype": "Sales Invoice", "reference_name": invoice, "docstatus": 1},
        extra_fields=["parent", "allocated_amount"],
    )
    for payment in row["payments"]:
        payment["payment_details"] = serialize(frappe.db.get_value(
            "Payment Entry", payment["parent"],
            ["posting_date", "mode_of_payment", "reference_no"], as_dict=True,
        ))

    return ok(data=row)


@frappe.whitelist()
def payment_schedule(booking=None):
    """Milestone plan across all bookings, or one booking if asked."""
    customer = get_customer()

    filters = {"customer": customer, "docstatus": ["<", 2]}
    if booking:
        assert_doc(customer, "Property Booking", booking)
        filters["name"] = booking

    bookings = frappe.get_all("Property Booking", filters=filters, pluck="name")
    if not bookings:
        return ok(data={"schedule": [], "total": 0})

    rows = get_list("Payment Plan", {"booking": ["in", bookings]}, order_by="due_date asc")
    for row in rows:
        paid = row.get("payment_status") == "Paid"
        row["status"] = "Paid" if paid else due_status(row.get("due_date"), flt(row.get("amount")))

    return ok(data={
        "schedule": rows,
        "total": len(rows),
        "total_amount": sum(flt(r.get("amount")) for r in rows),
        "total_unpaid": sum(flt(r.get("amount")) for r in rows if r["status"] != "Paid"),
    })
