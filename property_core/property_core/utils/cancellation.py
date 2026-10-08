"""What happens to the money when a booking is cancelled.

Cancelling used to release the unit and nothing else: the instalments kept
billing every night, the unpaid invoices kept being chased, and there was no
record of what the customer was owed back.

On cancel
  * instalments not yet billed are cancelled;
  * invoices with nothing received against them are cancelled (drafts deleted);
  * invoices part paid are closed for their unpaid part with a credit note, so
    the reminders stop;
  * what was collected, what the business keeps (Property Core Settings ->
    Forfeit on Cancellation) and what is owed back are written on the booking.

The refund itself is a separate, deliberate step -- money going out is never
automatic: ``make_refund`` raises a credit note for the refund and a Payment
Entry paying it to the customer.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from property_core.property_core.utils import settings


def close_out(booking):
    """Called from Property Booking on_cancel."""
    collected = 0.0

    for plan in frappe.get_all(
        "Payment Plan",
        filters={"booking": booking.name, "payment_status": ["!=", "Cancelled"]},
        fields=["name", "invoice"],
        order_by="due_date asc",
    ):
        paid = _close_plan(plan)
        collected += paid

    for plan in frappe.get_all(
        "Payment Plan",
        filters={"booking": booking.name, "late_fee_invoice": ["is", "set"]},
        pluck="late_fee_invoice",
    ):
        # a late fee already paid is kept; an unpaid one is withdrawn
        _close_invoice(plan)

    forfeit = min(_forfeit_for(booking, collected), collected)
    refund = flt(collected - forfeit, 2)

    booking.db_set({
        "cancellation_collected": flt(collected, 2),
        "cancellation_forfeit": flt(forfeit, 2),
        "cancellation_refund": refund,
        "refund_status": "Refund Due" if refund > 0 else "No Refund",
    })


def _close_plan(plan):
    # Cancelled first: withdrawing the invoice fires the status sync, which
    # would otherwise put the instalment back to Pending, ready to re-bill.
    frappe.db.set_value("Payment Plan", plan.name, "payment_status", "Cancelled", update_modified=False)
    paid = _close_invoice(plan.invoice) if plan.invoice else 0.0
    frappe.db.set_value(
        "Payment Plan", plan.name,
        {"paid_amount": paid, "outstanding_amount": 0},
        update_modified=False,
    )
    return paid


def _close_invoice(invoice):
    """Leave nothing outstanding on the invoice; return what was paid on it."""
    si = frappe.get_doc("Sales Invoice", invoice)
    if si.docstatus == 2:
        return 0.0
    if si.docstatus == 0:
        frappe.delete_doc("Sales Invoice", si.name, ignore_permissions=True)
        return 0.0

    outstanding = max(flt(si.outstanding_amount), 0)
    paid = flt(flt(si.grand_total) - outstanding, 2)
    if outstanding <= 0.005:
        return paid

    if paid <= 0.005:
        si.flags.ignore_permissions = True
        si.cancel()
        return 0.0

    _credit_note(si, outstanding, against=True, remarks=_("Unpaid balance withdrawn: booking cancelled"))
    return paid


def _credit_note(si, amount, against, remarks):
    """A credit note for ``amount`` on ``si``'s item.

    ``against`` -- reduce that invoice's outstanding (closing an unpaid balance);
    otherwise a standalone credit that leaves the customer in credit, to be
    paid out as a refund.
    """
    cn = frappe.new_doc("Sales Invoice")
    cn.customer = si.customer
    cn.company = si.company
    cn.posting_date = nowdate()
    cn.is_return = 1
    if against:
        cn.return_against = si.name
        # the field defaults to 1, which leaves the original invoice outstanding
        cn.update_outstanding_for_self = 0
    if cn.meta.has_field("property_unit") and si.get("property_unit"):
        cn.property_unit = si.property_unit
    item = si.items[0]
    rate = flt(amount, 2)
    if si.taxes and flt(si.grand_total):
        # the same taxes go on the credit note, so credit the net part
        cn.taxes_and_charges = si.taxes_and_charges
        for tax in si.taxes:
            cn.append("taxes", {k: tax.get(k) for k in (
                "charge_type", "account_head", "description", "rate", "cost_center", "included_in_print_rate",
            )})
        rate = flt(amount * flt(si.net_total) / flt(si.grand_total), 2)
    cn.append("items", {
        "item_code": item.item_code,
        "description": remarks,
        "qty": -1,
        "rate": rate,
        "income_account": item.income_account,
        "cost_center": item.cost_center,
    })
    cn.remarks = remarks
    cn.flags.ignore_permissions = True
    cn.insert()
    cn.submit()
    return cn


def _forfeit_for(booking, collected):
    basis = settings.get("cancellation_forfeit_basis") or "None"
    value = settings.get("cancellation_forfeit_value")
    if basis == "Booking Amount":
        return flt(booking.booking_amount)
    if basis == "Percentage of Agreement Value":
        return flt(booking.total_price) * value / 100
    if basis == "Percentage of Amount Paid":
        return collected * value / 100
    if basis == "Fixed Amount":
        return value
    return 0.0


@frappe.whitelist()
def make_refund(booking, mode_of_payment, posting_date=None, reference_no=None, reference_date=None, amount=None):
    """Pay back what a cancelled booking owes the customer.

    Raises a credit note for the refund (the sale income it reverses) and a
    Payment Entry paying it out. ``amount`` defaults to the refund worked out on
    cancel; give a different one if the agreement was settled otherwise.
    """
    doc = frappe.get_doc("Property Booking", booking)
    doc.check_permission("cancel")
    frappe.has_permission("Payment Entry", "create", throw=True)

    if doc.docstatus != 2:
        frappe.throw(_("Booking {0} is not cancelled").format(booking))
    if doc.refund_status == "Refunded":
        frappe.throw(_("Booking {0} is already refunded by {1}").format(booking, doc.refund_payment_entry))

    amount = flt(amount) if amount not in (None, "") else flt(doc.cancellation_refund)
    if amount <= 0:
        frappe.throw(_("Nothing to refund on booking {0}").format(booking))
    if amount > flt(doc.cancellation_collected) + 0.005:
        frappe.throw(
            _("Refund {0} is more than the {1} collected on this booking").format(
                frappe.format_value(amount, {"fieldtype": "Currency"}),
                frappe.format_value(doc.cancellation_collected, {"fieldtype": "Currency"}),
            )
        )

    template = _a_paid_invoice(booking)
    if not template:
        frappe.throw(_("No paid instalment invoice found on booking {0}").format(booking))

    cn = _credit_note(
        template, amount, against=False,
        remarks=_("Refund on cancellation of booking {0}").format(booking),
    )

    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

    pe = get_payment_entry("Sales Invoice", cn.name)
    pe.mode_of_payment = mode_of_payment
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account

    pe.paid_from = get_bank_cash_account(mode_of_payment, cn.company)["account"]
    pe.posting_date = posting_date or nowdate()
    pe.reference_no = reference_no or booking
    pe.reference_date = reference_date or pe.posting_date
    pe.remarks = _("Refund on cancellation of booking {0}").format(booking)
    pe.insert()
    pe.submit()

    doc.db_set({
        "refund_status": "Refunded",
        "refund_credit_note": cn.name,
        "refund_payment_entry": pe.name,
    })
    return {"credit_note": cn.name, "payment_entry": pe.name, "amount": amount}


def _a_paid_invoice(booking):
    for invoice in frappe.get_all(
        "Payment Plan",
        filters={"booking": booking, "invoice": ["is", "set"]},
        pluck="invoice",
        order_by="due_date desc",
    ):
        si = frappe.get_doc("Sales Invoice", invoice)
        if si.docstatus == 1 and not si.is_return:
            return si
