"""ERPNext Task -- the work list under a project (site visit, registration,
approval follow-up, handover prep …), assigned to people.

"Assigned" means the same thing as on the desk: an open ToDo. So a task given
out here shows in the assignee's desk ToDo list and bell, and one given out on
the desk shows here.
"""

import frappe
from frappe import _
from frappe.utils import today

from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "subject",
    "project",
    "status",
    "priority",
    "type",
    "exp_start_date",
    "exp_end_date",
    "progress",
    "parent_task",
    "is_group",
    "completed_on",
    "completed_by",
    "owner",
    "modified",
    "_assign",
]

WRITABLE = {
    "subject",
    "project",
    "status",
    "priority",
    "type",
    "exp_start_date",
    "exp_end_date",
    "expected_time",
    "progress",
    "parent_task",
    "is_group",
    "is_milestone",
    "description",
    "department",
    "issue",
}

DONE = ("Completed", "Cancelled", "Template")


@frappe.whitelist()
def get_tasks(
    project=None,
    status=None,
    assigned_to=None,
    mine=None,
    overdue=None,
    parent_task=None,
    search=None,
    filters=None,
    page=1,
    page_size=20,
    order_by=None,
):
    """``mine=1`` = assigned to me; ``assigned_to=user`` for someone else;
    ``overdue=1`` = past its end date and not done."""
    user = base.require_user()
    conditions = [["is_template", "=", 0]]
    if project:
        conditions.append(["project", "=", project])
    if status:
        values = base.parse(status, default=status)
        conditions.append(["status", "in", values if isinstance(values, list) else [values]])
    if parent_task:
        conditions.append(["parent_task", "=", parent_task])
    who = user if base.as_bool(mine) else assigned_to
    if who:
        conditions.append(["_assign", "like", f"%{who}%"])
    if base.as_bool(overdue):
        conditions += [["exp_end_date", "<", today()], ["status", "not in", DONE]]

    result = base.listing(
        "Task",
        LIST_FIELDS,
        filters=filters,
        extra_filters=conditions,
        search=search,
        search_fields=["subject", "name"],
        order_by=order_by or "exp_end_date asc, modified desc",
        page=page,
        page_size=page_size,
    )
    _with_assignees(result["rows"])
    return ok(data=result)


@frappe.whitelist()
def get_task(name):
    doc = base.read_doc("Task", name)
    payload = base.doc_payload(doc)
    payload["assigned_to"] = base.assignments("Task", [name]).get(name, [])
    payload["subtasks"] = base.serialize(
        frappe.get_list("Task", filters={"parent_task": name}, fields=["name", "subject", "status", "exp_end_date"])
    )
    payload["comments"] = base.serialize(
        frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Task", "reference_name": name, "comment_type": "Comment"},
            fields=["name", "content", "owner", "creation"],
            order_by="creation desc",
            limit=50,
        )
    )
    return ok(data=payload)


@frappe.whitelist()
def create_task(data=None, assign_to=None, **kwargs):
    """``assign_to``: a user, or a JSON list of users."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    if not payload.get("subject"):
        frappe.throw(_("A task needs a subject"), frappe.MandatoryError)
    doc = base.create_doc("Task", payload, WRITABLE, defaults={"status": "Open", "priority": "Medium"})
    _assign(doc, assign_to)
    return ok(data=_task_payload(doc.name), message=_("Task {0} created").format(doc.name))


@frappe.whitelist()
def update_task(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    doc, changed = base.write_doc("Task", name, payload, WRITABLE)
    return ok(data=_task_payload(name), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def set_status(name, status, note=None):
    doc = base.read_doc("Task", name)
    doc.check_permission("write")
    doc.status = status
    if status == "Completed":
        doc.progress = 100
    doc.save()
    if note:
        doc.add_comment("Comment", text=note)
    return ok(data=_task_payload(name), message=_("Task {0}: {1}").format(name, status))


@frappe.whitelist()
def assign_task(name, user, note=None, keep_others=0):
    """Give the task to ``user`` (a user or JSON list). By default the task has
    one owner and earlier assignees are released; ``keep_others=1`` adds."""
    doc = base.read_doc("Task", name)
    doc.check_permission("write")
    users = base.parse(user, default=user)
    users = users if isinstance(users, list) else [users]
    if base.as_bool(keep_others):
        _assign(doc, users, note)
    else:
        base.assign_to("Task", name, users[0], note)
        _assign(doc, users[1:], note)
    return ok(data=_task_payload(name), message=_("Assigned"))


@frappe.whitelist()
def unassign_task(name, user):
    from frappe.desk.form.assign_to import remove

    base.read_doc("Task", name).check_permission("write")
    remove("Task", name, user)
    return ok(data=_task_payload(name), message=_("Unassigned"))


@frappe.whitelist()
def delete_task(name):
    doc = base.read_doc("Task", name)
    doc.check_permission("delete")
    frappe.delete_doc("Task", name)
    return ok(data={"name": name}, message=_("Task deleted"))


@frappe.whitelist()
def options():
    base.require_user()
    meta = frappe.get_meta("Task")
    return ok(
        data={
            "statuses": [o for o in (meta.get_field("status").options or "").split("\n") if o and o != "Template"],
            "priorities": [o for o in (meta.get_field("priority").options or "").split("\n") if o],
            "types": frappe.get_all("Task Type", pluck="name", order_by="name asc"),
        }
    )


def _assign(doc, users, note=None):
    from frappe.desk.form.assign_to import add

    users = base.parse(users, default=users)
    if not users:
        return
    users = users if isinstance(users, list) else [users]
    add(
        {
            "doctype": "Task",
            "name": doc.name,
            "assign_to": users,
            "description": note or doc.subject,
            "date": doc.exp_end_date,
            "priority": {"Urgent": "High", "High": "High", "Low": "Low"}.get(doc.priority, "Medium"),
        }
    )


def _with_assignees(rows):
    assigned = base.assignments("Task", [r["name"] for r in rows])
    names = base.user_names([u for users in assigned.values() for u in users])
    for row in rows:
        row.pop("_assign", None)
        row["assigned_to"] = [{"user": u, "full_name": names.get(u) or u} for u in assigned.get(row["name"], [])]


def _task_payload(name):
    row = frappe.db.get_value("Task", name, LIST_FIELDS, as_dict=True)
    rows = base.serialize([row])
    _with_assignees(rows)
    return rows[0]
