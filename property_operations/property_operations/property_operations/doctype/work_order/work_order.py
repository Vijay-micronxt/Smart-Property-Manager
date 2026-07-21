import frappe
from frappe.model.document import Document
from frappe.utils import today


class WorkOrder(Document):
    def on_update(self):
        if self.maintenance_request:
            _sync_maintenance_request_status(self)

    def validate(self):
        if self.completed_date and self.scheduled_date:
            if self.completed_date < self.scheduled_date:
                frappe.throw(frappe._("Completed Date cannot be before Scheduled Date"))
        if self.status == "Completed" and not self.completed_date:
            self.completed_date = today()


def _sync_maintenance_request_status(wo):
    status_map = {
        "Assigned": "Assigned",
        "In Progress": "In Progress",
        "Completed": "Resolved",
        "Cancelled": "Open",
    }
    mr_status = status_map.get(wo.status)
    if mr_status:
        frappe.db.set_value(
            "Maintenance Request", wo.maintenance_request,
            {"status": mr_status, "work_order": wo.name},
            update_modified=False,
        )


def on_update(doc, method=None):
    pass
