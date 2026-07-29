import frappe
from frappe.model.document import Document


class CommissionRule(Document):
    def validate(self):
        if self.commission_rate <= 0:
            frappe.throw(frappe._("Commission Rate must be greater than zero"))
        if self.commission_type == "Percentage" and self.commission_rate > 100:
            frappe.throw(frappe._("Commission Rate cannot exceed 100% for Percentage type"))
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            frappe.throw(frappe._("Effective To cannot be before Effective From"))
