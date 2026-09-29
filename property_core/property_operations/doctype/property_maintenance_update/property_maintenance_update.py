"""One report from site on a maintenance task: a note, how far the work has
got, and the photos / video proving it (attached as ordinary Frappe files).

The newest update drives the task: its progress, and Open -> In Progress.
Completing is a separate, deliberate step (``complete``) because it checks
for proof -- an update saying "Completed" only lifts progress to 100.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

TASK = "Property Maintenance Task"


class PropertyMaintenanceUpdate(Document):
    def before_insert(self):
        self.posted_by = self.posted_by or frappe.session.user
        self.posted_on = self.posted_on or now_datetime()

    def validate(self):
        if self.progress is not None:
            self.progress = min(max(flt(self.progress), 0), 100)
        if self.update_type == "Completed" and not self.progress:
            self.progress = 100
        status = frappe.db.get_value(TASK, self.maintenance_task, "status")
        if status in ("Completed", "Cancelled") and self.is_new() and self.update_type != "Note":
            frappe.throw(frappe._("This task is {0}; only notes can be added.").format(status))

    def on_update(self):
        self.push_to_task()

    def after_delete(self):
        self.push_to_task()

    def push_to_task(self):
        latest = frappe.get_all(
            "Property Maintenance Update",
            filters={"maintenance_task": self.maintenance_task, "update_type": ["!=", "Note"]},
            fields=["progress", "posted_on"],
            order_by="posted_on desc, creation desc",
            limit=1,
        )
        status = frappe.db.get_value(TASK, self.maintenance_task, "status")
        values = {
            "progress": flt(latest[0].progress) if latest else 0,
            "last_update_on": latest[0].posted_on if latest else None,
        }
        if status == "Open" and latest:
            values["status"] = "In Progress"
        if status in ("Completed", "Cancelled"):
            values.pop("progress")
        frappe.db.set_value(TASK, self.maintenance_task, values, update_modified=False)
