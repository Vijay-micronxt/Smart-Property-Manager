import frappe
from frappe.utils import getdate, today
from frappe.model.document import Document


class PaymentPlan(Document):
    def validate(self):
        self.validate_amount()

    def validate_amount(self):
        if self.amount and self.amount <= 0:
            frappe.throw(frappe._("Amount must be greater than zero"))

    def generate_invoice(self):
        if self.invoice:
            frappe.throw(frappe._("Invoice already generated for this milestone"))

        booking = frappe.get_doc("Property Booking", self.booking)
        unit = frappe.get_doc("Property Unit", booking.property_unit)

        item_code = _resolve_item(unit)

        # An invoice raised today cannot have fallen due last month. An
        # overdue milestone kept failing ERPNext's "Due Date cannot be before
        # Posting Date" every single night, so it never billed at all -- the
        # milestone row already records how late it is.
        posting_date = getdate(today())
        due_date = max(getdate(self.due_date), posting_date)

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = booking.customer
        invoice.posting_date = posting_date
        invoice.due_date = due_date
        # Payment reminders default to "Property-Linked Invoices Only", so an
        # instalment invoice without this gets silently skipped by the chaser.
        if invoice.meta.has_field("property_unit"):
            invoice.property_unit = unit.name
        invoice.append("items", {
            "item_code": item_code,
            "description": "{} — {} ({})".format(
                self.milestone, unit.unit_number, unit.property
            ),
            "qty": 1,
            "rate": self.amount,
        })
        invoice.insert(ignore_permissions=True)

        # A draft carries no outstanding, so nothing downstream works: no
        # payment reminder, no Payment Entry against it, and the invoice
        # notification never fires. The customer is being asked to pay this, so
        # it has to be a real invoice.
        try:
            invoice.submit()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Payment Plan invoice left as draft: {self.name}"
            )

        self.db_set("invoice", invoice.name)
        self.db_set("payment_status", "Invoiced")

        return invoice.name


@frappe.whitelist()
def generate_invoice(payment_plan_name):
    doc = frappe.get_doc("Payment Plan", payment_plan_name)
    invoice_name = doc.generate_invoice()
    return invoice_name


def _resolve_item(unit):
    """The unit's own Item, else the one default sale item, else an Item named
    after the unit type. Without the settings fallback every unit needed its
    own Item before it could be invoiced, which stalled the whole payment plan.
    """
    candidates = [
        unit.item_code,
        frappe.db.get_single_value("Property Core Settings", "sale_item_code"),
        unit.unit_type,
    ]

    for candidate in candidates:
        if candidate and frappe.db.exists("Item", candidate):
            return candidate

    frappe.throw(
        frappe._(
            "No Item to invoice against for Property Unit {0}. "
            "Set 'Default Sale Item' in Property Core Settings, "
            "or set the ERPNext Item field on the unit itself."
        ).format(unit.name)
    )
