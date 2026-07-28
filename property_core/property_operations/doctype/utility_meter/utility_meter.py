import frappe
from frappe.model.document import Document


class UtilityMeter(Document):
    def validate(self):
        if self.rate_per_unit and self.rate_per_unit <= 0:
            frappe.throw(frappe._("Rate per Unit must be greater than zero"))
