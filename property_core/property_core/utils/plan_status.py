"""A Payment Plan instalment's status follows the money, whichever way it came in.

Only the Razorpay path used to mark an instalment Paid. Cash, cheque, NEFT, a
bank's loan disbursement or a receipt keyed in from the CRM all settled the
invoice in the books while the instalment stayed "Invoiced" for ever -- so the
portal kept showing the customer dues they had already paid.

The status is now read off the invoice after anything that can move its
outstanding: a Payment Entry, a Journal Entry, a credit note, the invoice being
cancelled, or advances reconciled onto it. A daily pass catches anything the
hooks did not see (Payment Reconciliation, a direct ledger repost).
"""

import frappe
from frappe.utils import flt, getdate, today

CLOSED_STATUSES = ("Paid", "Cancelled")


def sync_plan(name):
    plan = frappe.db.get_value(
        "Payment Plan", name,
        ["name", "booking", "invoice", "amount", "due_date", "payment_status",
         "paid_amount", "outstanding_amount"],
        as_dict=True,
    )
    if not plan or plan.payment_status == "Cancelled":
        return

    values = _values_for(plan)
    if any(_differs(plan.get(k), v) for k, v in values.items()):
        frappe.db.set_value("Payment Plan", name, values, update_modified=False)
        return plan.booking


def sync_invoice(invoice):
    """Every instalment billed on this invoice."""
    if not invoice:
        return
    bookings = set()
    for name in frappe.get_all("Payment Plan", filters={"invoice": invoice}, pluck="name"):
        bookings.add(sync_plan(name))
    _after_change(bookings)


def sync_booking(booking):
    for name in frappe.get_all("Payment Plan", filters={"booking": booking}, pluck="name"):
        sync_plan(name)
    _after_change({booking})


def _values_for(plan):
    amount = flt(plan.amount)
    if not plan.invoice:
        return {"payment_status": "Pending", "paid_amount": 0, "outstanding_amount": amount}

    si = frappe.db.get_value(
        "Sales Invoice", plan.invoice,
        ["docstatus", "grand_total", "outstanding_amount"],
        as_dict=True,
    )
    if not si or si.docstatus == 2:
        # the bill was withdrawn -- the instalment is owed again and can be re-billed
        return {"invoice": None, "payment_status": "Pending", "paid_amount": 0, "outstanding_amount": amount}

    if si.docstatus == 0:
        return {"payment_status": "Invoiced", "paid_amount": 0, "outstanding_amount": flt(si.grand_total)}

    outstanding = max(flt(si.outstanding_amount), 0)
    paid = max(flt(si.grand_total) - outstanding, 0)

    if outstanding <= 0.005:
        status = "Paid"
    elif plan.due_date and getdate(plan.due_date) < getdate(today()):
        status = "Overdue"
    elif paid > 0:
        status = "Partly Paid"
    else:
        status = "Invoiced"

    return {"payment_status": status, "paid_amount": paid, "outstanding_amount": outstanding}


def _differs(old, new):
    if isinstance(new, (int, float)):
        return abs(flt(old) - flt(new)) > 0.005
    return (old or None) != (new or None)


def _after_change(bookings):
    """Anything that depends on how much a booking has collected."""
    for booking in filter(None, bookings):
        for method in frappe.get_hooks("property_booking_collection_changed"):
            try:
                frappe.get_attr(method)(booking)
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"Collection change hook failed: {booking}")


# ------------------------------------------------------------------ #
# doc events
# ------------------------------------------------------------------ #

def on_payment_entry(doc, method=None):
    for row in doc.get("references") or []:
        if row.reference_doctype == "Sales Invoice":
            sync_invoice(row.reference_name)


def on_journal_entry(doc, method=None):
    for row in doc.get("accounts") or []:
        if row.reference_type == "Sales Invoice":
            sync_invoice(row.reference_name)


def on_sales_invoice(doc, method=None):
    sync_invoice(doc.name)
    if doc.get("return_against"):
        sync_invoice(doc.return_against)


def run_daily_sync():
    """Catch what the hooks missed, and roll unpaid instalments over to Overdue."""
    names = frappe.get_all(
        "Payment Plan",
        filters={"payment_status": ["not in", CLOSED_STATUSES], "invoice": ["is", "set"]},
        pluck="name",
    )
    bookings = set()
    for name in names:
        try:
            bookings.add(sync_plan(name))
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Payment Plan status sync failed: {name}")
    _after_change(bookings)
    frappe.db.commit()
