import frappe
from frappe.model.document import Document


class MaintenancePlanTemplate(Document):
    def validate(self):
        for row in self.schedule:
            if not row.month_no and not row.fixed_due_date:
                frappe.throw(
                    frappe._("Row {0}: set either Month No. or Fixed Due Date").format(row.idx)
                )
