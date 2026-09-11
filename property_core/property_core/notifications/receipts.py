"""Task 5 -- auto-reconcile customer payments and issue the receipt.

Reconciliation happens in ``validate`` rather than after submit on purpose: once
references are on the Payment Entry, ERPNext's own GL and outstanding-amount
logic does the rest, so invoice status and outstanding stay correct without this
app writing to them directly.

Nothing here may block a submit. A reconciliation problem is recorded on the
document and in the Error Log; the payment itself still goes through.
"""

import frappe
from frappe.utils import cstr, flt, getdate

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)
from property_core.property_core.notifications import channels as ch
from property_core.property_core.notifications import recipients as rc
from property_core.property_core.notifications.dispatcher import describe, notify

EVENT = "Payment Receipt"


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

def validate(doc, method=None):
    settings = get_settings()
    if not settings or not settings.enabled or not settings.auto_reconcile_payments:
        return
    if not _is_customer_receipt(doc):
        return
    if doc.get("custom_skip_auto_reconcile"):
        return
    if doc.references:
        return

    try:
        allocated = _auto_allocate(doc)
    except Exception:
        message = frappe.get_traceback()
        frappe.log_error(message, f"Payment Auto-Reconciliation Failed: {doc.name or 'new'}")
        doc.custom_reconciliation_error = message[-1000:]
        doc.custom_auto_reconciled = 0
        return

    doc.custom_reconciliation_error = None
    doc.custom_auto_reconciled = 1 if allocated else 0
    if not allocated:
        doc.custom_reconciliation_error = frappe._(
            "No outstanding Sales Invoice found for {0}; payment left unallocated."
        ).format(doc.party)


def _is_customer_receipt(doc):
    return doc.payment_type == "Receive" and doc.party_type == "Customer" and doc.party


def _auto_allocate(doc):
    """Spread the payment across open invoices, oldest due date first."""
    available = flt(doc.paid_amount)
    if available <= 0:
        return 0

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "customer": doc.party,
            "company": doc.company,
            "outstanding_amount": [">", 0],
            "is_return": 0,
        },
        fields=["name", "due_date", "posting_date", "grand_total", "outstanding_amount"],
        order_by="due_date asc, posting_date asc, name asc",
    )

    allocated_count = 0
    for invoice in invoices:
        if available <= 0:
            break

        allocation = min(available, flt(invoice.outstanding_amount))
        if allocation <= 0:
            continue

        doc.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice.name,
            "due_date": invoice.due_date,
            "total_amount": flt(invoice.grand_total),
            "outstanding_amount": flt(invoice.outstanding_amount),
            "allocated_amount": allocation,
        })
        available -= allocation
        allocated_count += 1

    if allocated_count:
        doc.set_amounts()

    return allocated_count


# --------------------------------------------------------------------------
# Receipt delivery
# --------------------------------------------------------------------------

def on_submit(doc, method=None):
    settings = get_settings()
    if not settings or not settings.enabled or not settings.send_receipt_on_payment:
        return
    if not _is_customer_receipt(doc):
        return
    if doc.get("custom_skip_property_notifications"):
        return

    _send_receipt(doc, settings, settings.receipt_channel or "Both", f"receipt::{doc.name}")


def _send_receipt(doc, settings, channel, dedupe_key):
    recipient = rc.for_customer(doc.party)
    if not recipient:
        return []

    attachment = None
    if settings.attach_receipt_pdf:
        needs_public = channel in ("Both", "WhatsApp") and settings.whatsapp_enabled
        try:
            file_url, file_name = ch.build_pdf_attachment(
                doc,
                print_format=settings.receipt_print_format,
                public=needs_public,
                label="Receipt",
            )
            attachment = {
                "file_url": file_url,
                "file_name": file_name,
                "public_url": ch.absolute_url(file_url) if needs_public else None,
            }
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Property Notification - Receipt PDF {doc.name}")

    return notify(
        event=EVENT,
        doc=doc,
        channel=channel,
        recipient=recipient,
        attachment=attachment,
        dedupe_key=dedupe_key,
        context={"allocated_invoices": allocation_summary(doc)},
    )


def allocation_summary(doc):
    """What this payment settled, with the balance left on each invoice."""
    rows = []
    for ref in doc.references or []:
        if ref.reference_doctype != "Sales Invoice":
            continue
        rows.append({
            "invoice": ref.reference_name,
            "allocated_amount": flt(ref.allocated_amount),
            "outstanding": flt(
                frappe.db.get_value("Sales Invoice", ref.reference_name, "outstanding_amount")
            ),
        })
    return rows


@frappe.whitelist()
def send_receipt_now(payment_entry_name, channel=None):
    from frappe.utils import now

    frappe.has_permission("Payment Entry", "read", doc=payment_entry_name, throw=True)

    settings = get_settings()
    if not settings or not settings.enabled:
        frappe.throw(frappe._("Property notifications are disabled in Property Notification Settings."))

    doc = frappe.get_doc("Payment Entry", payment_entry_name)
    if doc.docstatus != 1:
        frappe.throw(frappe._("Submit the payment before sending a receipt."))

    logs = _send_receipt(
        doc,
        settings,
        channel or settings.receipt_channel or "Both",
        f"receipt::{doc.name}::manual::{now()}",
    )
    return {"results": describe(logs)}


@frappe.whitelist()
def reconcile_now(payment_entry_name):
    """Retry reconciliation for a draft Payment Entry that failed earlier."""
    doc = frappe.get_doc("Payment Entry", payment_entry_name)
    doc.check_permission("write")

    if doc.docstatus != 0:
        frappe.throw(
            frappe._(
                "Payment Entry {0} is already submitted. Use Accounts > Payment Reconciliation "
                "to allocate it against invoices."
            ).format(payment_entry_name)
        )

    validate(doc)
    doc.save()
    return {
        "allocated": len(doc.references or []),
        "error": cstr(doc.custom_reconciliation_error or ""),
    }
