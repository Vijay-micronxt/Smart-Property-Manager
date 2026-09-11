"""Turn whatever the storefront posts into something payable.

The storefront sends a document id and expects a gateway order back. Before
property_core owned bookings that id was always a Sales Order, Sales Invoice or
Quotation, so both gateways hardcoded those three and threw on anything else --
which is why paying a booking came back as "Document BKG-0003 not found as
Sales Order, Sales Invoice, or Quotation".

A customer does not think in invoices. They open their booking and pay the
instalment that is due, so both of those resolve here:

  Property Booking -> its next unpaid instalment -> that instalment's invoice
  Payment Plan     -> its invoice, raised now if the due date has arrived and
                      nobody has billed it yet
"""

import frappe
from frappe import _

# Order matters: the first doctype holding the name wins.
PAYABLE_DOCTYPES = (
    "Sales Order",
    "Sales Invoice",
    "Quotation",
    "Property Booking",
    "Payment Plan",
)

PROPERTY_DOCTYPES = ("Property Booking", "Payment Plan")

UNPAID_STATUSES = ("Pending", "Invoiced", "Overdue")


def get_doctype(doc_name):
    for doctype in PAYABLE_DOCTYPES:
        if frappe.db.exists(doctype, doc_name):
            return doctype

    frappe.throw(
        _("{0} is not a Sales Order, Sales Invoice, Quotation, Property Booking or Payment Plan.").format(
            doc_name
        )
    )


def next_unpaid_instalment(booking_name):
    """The instalment the customer owes next -- earliest due, still unpaid."""
    rows = frappe.get_all(
        "Payment Plan",
        filters={"booking": booking_name, "payment_status": ["in", UNPAID_STATUSES]},
        fields=["name", "milestone", "due_date", "amount", "invoice"],
        order_by="due_date asc",
        limit=1,
    )
    return rows[0] if rows else None


def resolve_sales_invoice(doc_name, doctype=None):
    """The Sales Invoice to settle for a booking or an instalment.

    Raises the invoice if the instalment has none yet -- the daily billing job
    would do it on its own schedule, and a customer who wants to pay early
    should not have to wait for it.
    """
    doctype = doctype or get_doctype(doc_name)

    if doctype == "Payment Plan":
        plan = frappe.get_doc("Payment Plan", doc_name)
    elif doctype == "Property Booking":
        row = next_unpaid_instalment(doc_name)
        if not row:
            frappe.throw(
                _("Booking {0} has no unpaid instalment. Nothing to pay.").format(doc_name)
            )
        plan = frappe.get_doc("Payment Plan", row["name"])
    else:
        return None

    if plan.invoice:
        return plan.invoice

    return plan.generate_invoice()


def get_contact(doctype, doc):
    """(customer, email, phone) for the gateway's customer block."""
    customer = None

    if doctype == "Payment Plan":
        customer = frappe.db.get_value("Property Booking", doc.booking, "customer")
    else:
        customer = getattr(doc, "customer", None)

    email = getattr(doc, "contact_email", None)
    phone = getattr(doc, "contact_mobile", None)

    if customer and not (email and phone):
        values = frappe.db.get_value(
            "Customer", customer, ["email_id", "mobile_no"], as_dict=True
        ) or {}
        email = email or values.get("email_id")
        phone = phone or values.get("mobile_no")

    return customer, email, phone
