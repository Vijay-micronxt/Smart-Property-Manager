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

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = booking.customer
        invoice.due_date = self.due_date
        invoice.append("items", {
            "item_code": unit.unit_type,
            "description": f"{self.milestone} - {unit.unit_number}",
            "qty": 1,
            "rate": self.amount,
        })
        invoice.insert(ignore_permissions=True)

        self.db_set("invoice", invoice.name)
        self.db_set("payment_status", "Invoiced")

        return invoice.name
