"""One maintenance visit on one unit: what has to be done, who is doing it,
how far they got, and the photos proving it was done.

Opened automatically a few days before each maintenance date on the unit's
Maintenance Plan Template (see ``utils/maintenance_tasks.py``), or by hand for
anything off-schedule. Replaces the Work Order the billing run used to open:
"Work Order" is also ERPNext Manufacturing's doctype, and on sites that
override its controller (JD) every insert failed.

Progress and proof arrive as Property Maintenance Update records; the newest
one drives ``progress`` / ``status`` here. Completing needs at least one proof
file unless Property Core Settings says otherwise.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime, today

UPDATE = "Property Maintenance Update"
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif")
VIDEO_TYPES = (".mp4", ".mov", ".webm", ".m4v", ".3gp", ".avi")


class PropertyMaintenanceTask(Document):
    def validate(self):
        if not self.subject:
            self.subject = _("Maintenance - {0}").format(self.unit_number or self.property_unit)
        if self.status == "Completed":
            if not self.completed_on:
                self.completed_on = getdate(today())
            self.completed_by = self.completed_by or frappe.session.user
            self.progress = 100
            if self.has_value_changed("status") and proof_required() and not proof_files(self.name):
                frappe.throw(
                    _("Attach at least one photo or file as proof before completing this task."),
                    title=_("Proof needed"),
                )
        elif self.status in ("Open", "In Progress"):
            self.completed_on = None
            self.completed_by = None

    def on_update(self):
        if self.has_value_changed("assigned_to"):
            sync_assignment(self)
        if self.status in ("Completed", "Cancelled"):
            close_assignments(self)


def proof_required():
    value = frappe.db.get_single_value("Property Core Settings", "maintenance_proof_required")
    return True if value is None else bool(cint(value))


def proof_files(task):
    """Every file proving work on this task -- on the task itself or on any of
    its updates -- tagged image / video / file."""
    updates = frappe.get_all(UPDATE, filters={"maintenance_task": task}, pluck="name")
    rows = frappe.get_all(
        "File",
        filters=[
            ["is_folder", "=", 0],
            ["attached_to_doctype", "in", ["Property Maintenance Task", UPDATE]],
            ["attached_to_name", "in", [task] + updates],
        ],
        fields=["name", "file_name", "file_url", "file_size", "is_private", "attached_to_doctype",
                "attached_to_name", "creation"],
        order_by="creation asc",
    )
    for row in rows:
        row["kind"] = file_kind(row.file_name)
        row["update"] = row.attached_to_name if row.attached_to_doctype == UPDATE else None
    return rows


def file_kind(file_name):
    lowered = (file_name or "").lower()
    if lowered.endswith(IMAGE_TYPES):
        return "image"
    if lowered.endswith(VIDEO_TYPES):
        return "video"
    return "file"


def sync_assignment(doc):
    """The assignee sees the task in their desk ToDo / bell, same as any
    other assignment."""
    from frappe.desk.form.assign_to import add, remove

    for row in frappe.get_all(
        "ToDo",
        filters={"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"},
        pluck="allocated_to",
    ):
        if row != doc.assigned_to:
            remove(doc.doctype, doc.name, row, ignore_permissions=True)
    if doc.assigned_to and doc.status not in ("Completed", "Cancelled"):
        add(
            {
                "doctype": doc.doctype,
                "name": doc.name,
                "assign_to": [doc.assigned_to],
                "description": doc.subject,
                "date": doc.scheduled_date,
            },
            ignore_permissions=True,
        )


def close_assignments(doc):
    frappe.db.set_value(
        "ToDo",
        {"reference_type": doc.doctype, "reference_name": doc.name, "status": "Open"},
        "status",
        "Closed",
        update_modified=False,
    )


def updates_of(task):
    rows = frappe.get_all(
        UPDATE,
        filters={"maintenance_task": task},
        fields=["name", "update_type", "progress", "note", "posted_on", "posted_by"],
        order_by="posted_on desc, creation desc",
    )
    files = {}
    for f in proof_files(task):
        files.setdefault(f["update"] or "", []).append(f)
    for row in rows:
        row["posted_by_name"] = frappe.db.get_value("User", row.posted_by, "full_name") or row.posted_by
        row["proof"] = files.get(row.name, [])
    return rows, files.get("", [])


# --------------------------------------------------------------------------- #
# desk calls
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_updates(task):
    frappe.has_permission("Property Maintenance Task", "read", doc=task, throw=True)
    rows, task_files = updates_of(task)
    return {"updates": rows, "task_files": task_files, "proof_required": proof_required()}


@frappe.whitelist()
def post_update(task, note=None, progress=None, update_type="Progress"):
    """Log progress from site. Returns the update to attach proof files to."""
    frappe.has_permission("Property Maintenance Task", "write", doc=task, throw=True)
    doc = frappe.get_doc(
        {
            "doctype": UPDATE,
            "maintenance_task": task,
            "update_type": update_type,
            "progress": progress if progress not in (None, "") else None,
            "note": note,
        }
    ).insert()
    return {"name": doc.name, "status": frappe.db.get_value("Property Maintenance Task", task, "status")}


@frappe.whitelist()
def complete(task, work_done=None):
    doc = frappe.get_doc("Property Maintenance Task", task)
    doc.check_permission("write")
    doc.status = "Completed"
    if work_done:
        doc.work_done = work_done
    doc.save()
    return doc.name
