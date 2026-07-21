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

        item_code = unit.item_code or unit.unit_type
        if not frappe.db.exists("Item", item_code):
            frappe.throw(
                frappe._(
                    "ERPNext Item '{0}' not found. "
                    "Please create an Item named '{0}' in ERPNext Stock → Items, "
                    "then set it in the 'ERPNext Item' field on Property Unit {1}."
                ).format(item_code, unit.name)
            )

        invoice = frappe.new_doc("Sales Invoice")
        invoice.customer = booking.customer
        invoice.due_date = self.due_date
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
