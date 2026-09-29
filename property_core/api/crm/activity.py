"""Comments, assignment and the timeline on any record the CRM app shows --
what the desk's form sidebar and timeline do.

Assignment is Frappe's own (an open ToDo): it shows in the assignee's desk
ToDo list and notifications either way.
"""

import frappe
from frappe import _

from property_core.api.crm import base
from property_core.api.crm.files import ATTACHABLE
from property_core.api.utils import ok


def _doc(doctype, name, ptype="read"):
    if doctype not in ATTACHABLE:
        frappe.throw(_("{0} is not available through this API").format(doctype), frappe.PermissionError)
    doc = base.read_doc(doctype, name)
    if ptype != "read":
        doc.check_permission(ptype)
    return doc


@frappe.whitelist()
def add_comment(doctype, name, text):
    doc = _doc(doctype, name)
    if not (text or "").strip():
        frappe.throw(_("Write something"))
    comment = doc.add_comment("Comment", text=text)
    return ok(data={"name": comment.name, "content": comment.content, "creation": str(comment.creation)})


@frappe.whitelist()
def get_comments(doctype, name, limit=50):
    _doc(doctype, name)
    rows = frappe.get_all(
        "Comment",
        filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
        fields=["name", "content", "owner", "comment_email", "creation"],
        order_by="creation desc",
        limit=int(limit or 50),
    )
    names = base.user_names([r.owner for r in rows])
    for row in rows:
        row["full_name"] = names.get(row.owner) or row.owner
    return ok(data=base.serialize(rows))


@frappe.whitelist()
def timeline(doctype, name, limit=50):
    """Comments, assignments, attachments, field changes and communications
    on the record, newest first."""
    _doc(doctype, name)
    limit = int(limit or 50)
    events = []
    for c in frappe.get_all(
        "Comment",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["comment_type", "content", "owner", "creation"],
        order_by="creation desc",
        limit=limit,
    ):
        events.append({"type": c.comment_type, "text": c.content, "by": c.owner, "at": c.creation})
    for v in frappe.get_all(
        "Version",
        filters={"ref_doctype": doctype, "docname": name},
        fields=["data", "owner", "creation"],
        order_by="creation desc",
        limit=limit,
    ):
        changed = (frappe.parse_json(v.data) or {}).get("changed") or []
        if changed:
            events.append(
                {
                    "type": "Changed",
                    "changes": [{"field": f, "from": a, "to": b} for f, a, b in changed],
                    "by": v.owner,
                    "at": v.creation,
                }
            )
    for m in frappe.get_all(
        "Communication",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["communication_medium", "subject", "sender", "sent_or_received", "creation"],
        order_by="creation desc",
        limit=limit,
    ):
        events.append(
            {
                "type": m.communication_medium or "Communication",
                "text": m.subject,
                "by": m.sender,
                "direction": m.sent_or_received,
                "at": m.creation,
            }
        )
    events.sort(key=lambda e: e["at"], reverse=True)
    names = base.user_names([e.get("by") for e in events])
    for e in events:
        e["by_name"] = names.get(e.get("by")) or e.get("by")
    return ok(data=base.serialize(events[:limit]))


@frappe.whitelist()
def assign(doctype, name, user, note=None):
    """One working owner: earlier open assignments are released."""
    _doc(doctype, name, "write")
    base.assign_to(doctype, name, user, note)
    return ok(data={"assigned_to": base.assignments(doctype, [name]).get(name, [])}, message=_("Assigned"))


@frappe.whitelist()
def unassign(doctype, name, user):
    from frappe.desk.form.assign_to import remove

    _doc(doctype, name, "write")
    remove(doctype, name, user)
    return ok(data={"assigned_to": base.assignments(doctype, [name]).get(name, [])}, message=_("Unassigned"))


@frappe.whitelist()
def my_assignments(status="Open", reference_type=None, page=1, page_size=20):
    """Everything assigned to me (desk ToDo), across records."""
    user = base.require_user()
    filters = [["allocated_to", "=", user], ["status", "=", status]]
    if reference_type:
        filters.append(["reference_type", "=", reference_type])
    page, page_size, start = base.page_args(page, page_size)
    rows = frappe.get_all(
        "ToDo",
        filters=filters,
        fields=["name", "reference_type", "reference_name", "description", "date", "priority", "assigned_by", "creation"],
        order_by="date asc, creation desc",
        limit_start=start,
        limit_page_length=page_size,
    )
    return ok(data={"rows": base.serialize(rows), "page": page, "page_size": page_size})
