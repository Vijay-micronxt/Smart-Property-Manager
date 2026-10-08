import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CommissionRule(Document):
    def validate(self):
        if flt(self.commission_rate) <= 0:
            frappe.throw(frappe._("Commission Rate must be greater than zero"))
        if self.commission_type == "Percentage" and flt(self.commission_rate) > 100:
            frappe.throw(frappe._("Commission Rate cannot exceed 100% for Percentage type"))
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            frappe.throw(frappe._("Effective To cannot be before Effective From"))
        self.validate_release_stages()

    def validate_release_stages(self):
        """Stages are cumulative: "at 20% paid, 50% released; at 100%, 100%"."""
        self.release_stages.sort(key=lambda r: flt(r.customer_paid_percent))
        last = 0
        for idx, row in enumerate(self.release_stages, start=1):
            row.idx = idx
            if not 0 <= flt(row.customer_paid_percent) <= 100 or not 0 < flt(row.release_percent) <= 100:
                frappe.throw(frappe._("Row {0}: percentages must be between 0 and 100").format(idx))
            if flt(row.release_percent) < last:
                frappe.throw(
                    frappe._("Row {0}: commission released cannot go down as the customer pays more").format(idx)
                )
            last = flt(row.release_percent)
        if self.release_stages and last < 100:
            frappe.throw(frappe._("The last release stage must release 100% of the commission"))
