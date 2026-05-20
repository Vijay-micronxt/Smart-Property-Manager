import frappe
from frappe.model.document import Document


class PropertyAgreement(Document):
    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(frappe._("End Date cannot be before Start Date"))
