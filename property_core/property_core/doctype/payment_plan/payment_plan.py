import frappe
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

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = booking.customer
        invoice.due_date = self.due_date
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
