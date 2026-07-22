import frappe
from frappe.model.document import Document
from frappe.utils import today


class MaintenanceRequest(Document):
    def before_save(self):
        if not self.raised_on:
            self.raised_on = today()
        if self.status in ("Resolved", "Closed") and not self.resolved_on:
            self.resolved_on = today()
