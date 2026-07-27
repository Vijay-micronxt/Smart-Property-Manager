import frappe
from frappe.model.document import Document


class PaymentPlanTemplate(Document):
    def validate(self):
        self.validate_percentages()

    def validate_percentages(self):
        total = sum(row.percentage for row in self.milestones)
        if abs(total - 100) > 0.01:
            frappe.throw(
                frappe._("Milestone percentages must total 100%. Current total: {0}%").format(total)
            )
