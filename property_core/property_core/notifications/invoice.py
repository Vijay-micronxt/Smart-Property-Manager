"""Task 1 -- deliver the Sales Invoice PDF to the customer on submit."""

import frappe

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)
from property_core.property_core.notifications import channels as ch
from property_core.property_core.notifications import recipients as rc
from property_core.property_core.notifications.dispatcher import describe, notify

EVENT = "Sales Invoice"


def on_submit(doc, method=None):
    settings = get_settings()
    if not settings or not settings.enabled or not settings.send_invoice_on_submit:
        return
    if doc.get("is_return") or doc.get("custom_skip_property_notifications"):
        return

    _send(doc, settings, settings.invoice_channel or "Both")


def _send(doc, settings, channel):
    recipient = rc.for_customer(doc.customer)
    if not recipient:
        frappe.log_error(
            f"Customer {doc.customer} not found while sending invoice {doc.name}",
            "Property Notification - Invoice",
        )
        return []

    attachment = None
    if settings.attach_invoice_pdf:
        attachment = _build_attachment(doc, settings, channel)

    return notify(
        event=EVENT,
        doc=doc,
        channel=channel,
        recipient=recipient,
        attachment=attachment,
        context={"property_unit": rc.property_unit_label(linked_property_unit(doc.name))},
        dedupe_key=f"invoice::{doc.name}",
    )


def _build_attachment(doc, settings, channel):
    """PDF once, reused by both channels.

    WhatsApp providers download the file over anonymous HTTP, so when WhatsApp
    is in play the file has to be public; email-only stays private.
    """
    needs_public = channel in ("Both", "WhatsApp") and settings.whatsapp_enabled

    try:
        file_url, file_name = ch.build_pdf_attachment(
            doc, print_format=settings.invoice_print_format, public=needs_public, label="Invoice"
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Property Notification - Invoice PDF {doc.name}")
        return None

    return {
        "file_url": file_url,
        "file_name": file_name,
        "public_url": ch.absolute_url(file_url) if needs_public else None,
    }


def linked_property_unit(invoice_name):
    """Which unit an invoice belongs to, whichever engine raised it.

    Maintenance and rent runs stamp `property_unit` directly; Payment Plan
    milestones reach it through the booking. Anything hand-raised relies on the
    user filling `property_unit` in.
    """
    direct = frappe.db.get_value("Sales Invoice", invoice_name, "property_unit")
    if direct:
        return direct

    booking = frappe.db.get_value("Payment Plan", {"invoice": invoice_name}, "booking")
    if booking:
        return frappe.db.get_value("Property Booking", booking, "property_unit")

    allocation = frappe.db.get_value("Rent Invoice Log", {"invoice": invoice_name}, "allocation")
    if allocation:
        return frappe.db.get_value("Property Allocation", allocation, "property_unit")

    return None


@frappe.whitelist()
def send_now(invoice_name, channel=None):
    """Manual send/resend from the Sales Invoice form."""
    frappe.has_permission("Sales Invoice", "read", doc=invoice_name, throw=True)

    settings = get_settings()
    if not settings or not settings.enabled:
        frappe.throw(frappe._("Property notifications are disabled in Property Notification Settings."))

    doc = frappe.get_doc("Sales Invoice", invoice_name)
    if doc.docstatus != 1:
        frappe.throw(frappe._("Submit the invoice before sending it."))

    # A manual send is an explicit instruction, so it bypasses the dedupe guard
    # that stops the automatic path from sending twice.
    logs = _send_forced(doc, settings, channel or settings.invoice_channel or "Both")
    return {"results": describe(logs)}


def _send_forced(doc, settings, channel):
    from frappe.utils import now

    attachment = _build_attachment(doc, settings, channel) if settings.attach_invoice_pdf else None
    recipient = rc.for_customer(doc.customer)
    return notify(
        event=EVENT,
        doc=doc,
        channel=channel,
        recipient=recipient,
        attachment=attachment,
        context={"property_unit": rc.property_unit_label(linked_property_unit(doc.name))},
        dedupe_key=f"invoice::{doc.name}::manual::{now()}",
    )
