import frappe
from frappe.model.document import Document
from frappe.utils import today


class MaintenanceRequest(Document):
    def validate(self):
        if self.current_reading and self.previous_reading:
            if self.current_reading < self.previous_reading:
                frappe.throw(frappe._("Current reading cannot be less than previous reading"))

    def before_save(self):
        if not self.raised_on:
            self.raised_on = today()
        if self.status in ("Resolved", "Closed") and not self.resolved_on:
            self.resolved_on = today()
