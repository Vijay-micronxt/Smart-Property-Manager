"""One report from site: how far the job has got, and the photos proving it.

Maintenance used to end at a Sales Invoice. Nobody could see whether the work
had actually been done, so this is the trail the customer and the office read:
each update carries a percentage, a note and whatever the worker photographed
or filmed, and the newest one drives the Work Order's own status.

Proof files are ordinary Frappe attachments on this record, uploaded through
frappe.handler's upload_file with doctype=Work Order Update. Nothing custom --
that path already handles multipart, size limits and private files, and the
File permission check then follows the Work Order.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif")
VIDEO_TYPES = (".mp4", ".mov", ".webm", ".m4v", ".3gp", ".avi")


class WorkOrderUpdate(frappe.model.document.Document):
    def before_insert(self):
        self.posted_by = self.posted_by or frappe.session.user
        self.posted_on = self.posted_on or now_datetime()

    def validate(self):
        if self.progress is not None:
            self.progress = min(max(flt(self.progress), 0), 100)
        if self.update_type == "Completed" and not self.progress:
            self.progress = 100

    def on_update(self):
        self.push_to_work_order()

    def after_delete(self):
        self.push_to_work_order()

    def push_to_work_order(self):
        """The work order shows the latest word from site, not the first."""
        if not self.work_order:
            return

        latest = frappe.get_all(
            "Work Order Update",
            filters={"work_order": self.work_order},
            fields=["progress", "update_type", "posted_on"],
            order_by="posted_on desc, creation desc",
            limit=1,
        )
        if not latest:
            frappe.db.set_value(
                "Work Order", self.work_order,
                {"progress": 0, "last_update_on": None}, update_modified=False,
            )
            return

        row = latest[0]
        values = {"progress": flt(row.progress), "last_update_on": row.posted_on}

        status = frappe.db.get_value("Work Order", self.work_order, "status")
        if status not in ("Completed", "Cancelled"):
            if flt(row.progress) >= 100 or row.update_type == "Completed":
                values["status"] = "Completed"
                values["completed_date"] = frappe.utils.getdate(row.posted_on)
            elif status in ("Draft", "Assigned"):
                values["status"] = "In Progress"

        frappe.db.set_value("Work Order", self.work_order, values, update_modified=False)


def proof_files(update_name):
    """Attachments on one update, split into pictures and video."""
    rows = frappe.get_all(
        "File",
        filters={"attached_to_doctype": "Work Order Update", "attached_to_name": update_name},
        fields=["name", "file_name", "file_url", "file_size", "is_private", "creation"],
        order_by="creation asc",
    )

    for row in rows:
        lowered = (row.get("file_name") or "").lower()
        if lowered.endswith(IMAGE_TYPES):
            row["kind"] = "image"
        elif lowered.endswith(VIDEO_TYPES):
            row["kind"] = "video"
        else:
            row["kind"] = "file"

    return rows


@frappe.whitelist()
def post_update(work_order, progress=None, note=None, update_type="Progress"):
    """Log an update from site. Returns the name to attach proof files to.

    The caller then uploads each photo or clip to
    ``/api/method/upload_file`` with ``doctype=Work Order Update`` and
    ``docname=`` the name returned here.
    """
    frappe.has_permission("Work Order", "write", doc=work_order, throw=True)

    doc = frappe.get_doc(
        {
            "doctype": "Work Order Update",
            "work_order": work_order,
            "update_type": update_type,
            "progress": flt(progress) if progress not in (None, "") else None,
            "note": note,
        }
    )
    doc.insert()

    return {
        "name": doc.name,
        "work_order": doc.work_order,
        "progress": doc.progress,
        "work_order_status": frappe.db.get_value("Work Order", work_order, "status"),
        "upload_to": "/api/method/upload_file",
        "upload_args": {
            "doctype": "Work Order Update",
            "docname": doc.name,
            "is_private": 1,
        },
    }


@frappe.whitelist()
def updates(work_order):
    """Every update on a work order, newest first, with its proof."""
    frappe.has_permission("Work Order", "read", doc=work_order, throw=True)

    rows = frappe.get_all(
        "Work Order Update",
        filters={"work_order": work_order},
        fields=["name", "update_type", "progress", "note", "posted_on", "posted_by"],
        order_by="posted_on desc",
    )
    for row in rows:
        row["posted_by_name"] = frappe.db.get_value("User", row.posted_by, "full_name") or row.posted_by
        row["proof"] = proof_files(row.name)

    return rows
