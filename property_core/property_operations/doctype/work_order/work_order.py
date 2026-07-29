import frappe
from frappe.model.document import Document
from frappe.utils import today


class WorkOrder(Document):
    def on_update(self):
        if self.issue:
            _sync_issue_status(self)

    def validate(self):
        if self.completed_date and self.scheduled_date:
            if self.completed_date < self.scheduled_date:
                frappe.throw(frappe._("Completed Date cannot be before Scheduled Date"))
        if self.status == "Completed" and not self.completed_date:
            self.completed_date = today()


def _sync_issue_status(wo):
    """Issue's own status (Open/Replied/On Hold/Resolved/Closed) doesn't map
    cleanly onto Work Order's dispatch states (Assigned/In Progress/...) --
    Work Order's own status already tracks that granularity for staff. Only
    flip the linked Issue to Resolved once the work is actually Completed.
    """
    frappe.db.set_value("Issue", wo.issue, "work_order", wo.name, update_modified=False)
    if wo.status == "Completed":
        frappe.db.set_value(
            "Issue", wo.issue,
            {"status": "Resolved", "resolution_details": wo.description},
            update_modified=False,
        )


def on_update(doc, method=None):
    pass
