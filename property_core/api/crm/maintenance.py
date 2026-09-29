"""Maintenance visits on units: the Property Maintenance Task list, progress
from site with photo / video / file proof, and completion.

Tasks open by themselves a few days before each maintenance date on the
unit's Maintenance Plan Template (Property Core Settings sets how many days,
who they go to and whether proof is required to complete). ``create_task`` is
for anything off-schedule.

Proof is sent with the call -- multipart ``file`` (one or many) or base64
``files: [{filename, content}]`` -- and lands as attachments on the update, so
the desk, this API and the customer portal all show the same pictures.
"""

import base64

import frappe
from frappe import _
from frappe.utils import add_days, today

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_operations.doctype.property_maintenance_task.property_maintenance_task import (
    proof_files,
    proof_required,
    updates_of,
)

TASK = "Property Maintenance Task"
UPDATE = "Property Maintenance Update"

LIST_FIELDS = [
    "name",
    "subject",
    "property_unit",
    "unit_number",
    "property",
    "project",
    "customer",
    "status",
    "scheduled_date",
    "assigned_to",
    "progress",
    "last_update_on",
    "maintenance_period",
    "charge_amount",
    "sales_invoice",
    "source",
    "completed_on",
    "show_to_customer",
]

WRITABLE = {"subject", "property_unit", "scheduled_date", "assigned_to", "description", "show_to_customer"}

MAX_BYTES = 25 * 1024 * 1024


@frappe.whitelist()
def get_tasks(
    property_unit=None,
    property=None,
    project=None,
    customer=None,
    status=None,
    mine=None,
    assigned_to=None,
    overdue=None,
    from_date=None,
    to_date=None,
    search=None,
    page=1,
    page_size=20,
    order_by=None,
):
    """``overdue=1`` = date passed and not done; ``mine=1`` = assigned to me."""
    user = base.require_user()
    conditions = []
    for field, value in (("property_unit", property_unit), ("property", property), ("project", project),
                         ("customer", customer)):
        if value:
            conditions.append([field, "=", value])
    if status:
        values = base.parse(status, default=status)
        conditions.append(["status", "in", values if isinstance(values, list) else [values]])
    who = user if base.as_bool(mine) else assigned_to
    if who:
        conditions.append(["assigned_to", "=", who])
    if base.as_bool(overdue):
        conditions += [["scheduled_date", "<", today()], ["status", "in", ["Open", "In Progress"]]]
    base.date_range(conditions, "scheduled_date", from_date, to_date)

    result = base.listing(
        TASK,
        LIST_FIELDS,
        extra_filters=conditions,
        search=search,
        search_fields=["name", "subject", "unit_number"],
        order_by=order_by or "scheduled_date asc",
        page=page,
        page_size=page_size,
    )
    _decorate(result["rows"])
    return ok(data=result)


@frappe.whitelist()
def get_task(name):
    doc = base.read_doc(TASK, name)
    payload = base.doc_payload(doc)
    updates, task_files = updates_of(name)
    payload["updates"] = base.serialize(updates)
    payload["task_files"] = base.serialize(task_files)
    payload["proof_count"] = len(proof_files(name))
    payload["proof_required"] = proof_required()
    payload["assigned_to_name"] = base.user_names([doc.assigned_to]).get(doc.assigned_to)
    return ok(data=payload)


@frappe.whitelist()
def create_task(data=None, **kwargs):
    """A visit off the schedule (a repair, a one-off clean-up …)."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    if not payload.get("property_unit"):
        frappe.throw(_("A maintenance task needs a unit"), frappe.MandatoryError)
    doc = base.create_doc(TASK, payload, WRITABLE, defaults={"source": "Manual", "status": "Open",
                                                             "scheduled_date": today()})
    return ok(data=base.doc_payload(doc), message=_("Maintenance task {0} created").format(doc.name))


@frappe.whitelist()
def update_task(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    doc, changed = base.write_doc(TASK, name, payload, WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def assign(name, user):
    doc = base.read_doc(TASK, name)
    doc.check_permission("write")
    doc.assigned_to = user
    doc.save()
    return ok(data={"name": name, "assigned_to": user}, message=_("Assigned"))


@frappe.whitelist()
def post_update(name, note=None, progress=None, update_type="Progress", files=None, filename=None, content=None):
    """Progress from site. ``update_type``: Progress / Blocked / Note.
    Proof: multipart ``file`` (repeatable), or ``files: [{filename, content}]``
    base64, or a single ``filename`` + ``content``."""
    doc = base.read_doc(TASK, name)
    doc.check_permission("write")
    if update_type not in ("Progress", "Blocked", "Note"):
        frappe.throw(_("update_type must be Progress, Blocked or Note -- use complete to finish"))
    update = frappe.get_doc(
        {
            "doctype": UPDATE,
            "maintenance_task": name,
            "update_type": update_type,
            "progress": progress if progress not in (None, "") else None,
            "note": note,
        }
    ).insert()
    attached = _attach_all(UPDATE, update.name, files, filename, content)
    return ok(
        data={"update": update.name, "proof": attached, **_brief(name)},
        message=_("Update posted"),
    )


@frappe.whitelist()
def complete(name, work_done=None, files=None, filename=None, content=None):
    """Finish the visit. Proof sent here is attached first, so one call can
    carry the photos and close the task."""
    doc = base.read_doc(TASK, name)
    doc.check_permission("write")
    if doc.status == "Completed":
        return ok(data=_brief(name), message=_("Already completed"))

    attached = []
    if files or content or _multipart():
        update = frappe.get_doc(
            {"doctype": UPDATE, "maintenance_task": name, "update_type": "Completed", "progress": 100,
             "note": work_done}
        ).insert()
        attached = _attach_all(UPDATE, update.name, files, filename, content)

    doc.reload()
    doc.status = "Completed"
    if work_done:
        doc.work_done = work_done
    doc.save()
    return ok(data={**_brief(name), "proof": attached}, message=_("Maintenance completed"))


@frappe.whitelist()
def cancel(name, reason=None):
    doc = base.read_doc(TASK, name)
    doc.check_permission("write")
    doc.status = "Cancelled"
    doc.save()
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(data=_brief(name), message=_("Task cancelled"))


@frappe.whitelist()
def reopen(name, reason=None):
    doc = base.read_doc(TASK, name)
    doc.check_permission("write")
    doc.status = "In Progress" if doc.progress else "Open"
    doc.save()
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(data=_brief(name), message=_("Task reopened"))


@frappe.whitelist()
def unit_history(property_unit):
    """Everything maintenance on one unit: the schedule (charges, billed or
    to come) and every visit with its updates and proof."""
    base.read_doc("Property Unit", property_unit)
    from property_core.property_operations.utils.maintenance_schedule import project_schedule

    tasks = frappe.get_list(TASK, filters={"property_unit": property_unit}, fields=LIST_FIELDS,
                            order_by="scheduled_date desc")
    for task in tasks:
        updates, task_files = updates_of(task.name)
        task["updates"] = updates
        task["task_files"] = task_files
    return ok(
        data={
            "property_unit": property_unit,
            "schedule": base.serialize(project_schedule(property_unit, months_ahead=12)),
            "tasks": base.serialize(tasks),
            "summary": {
                "completed": sum(1 for t in tasks if t.status == "Completed"),
                "open": sum(1 for t in tasks if t.status in ("Open", "In Progress")),
                "overdue": sum(1 for t in tasks if t.status in ("Open", "In Progress")
                               and str(t.scheduled_date) < today()),
            },
        }
    )


@frappe.whitelist()
def generate_now(property_unit=None, property=None):
    """Open whatever visits are due in the lead window now, without waiting for
    the nightly run -- one unit, or every unit of a property."""
    base.require_user()
    from property_core.property_operations.utils.maintenance_tasks import generate_for_unit

    units = [property_unit] if property_unit else frappe.get_list(
        "Property Unit", filters={"property": property, "maintenance_plan_template": ["is", "set"]}, pluck="name"
    ) if property else []
    if not units:
        frappe.throw(_("Give a property_unit or a property"), frappe.MandatoryError)
    created = []
    for unit in units:
        base.read_doc("Property Unit", unit).check_permission("write")
        created += generate_for_unit(unit)
    return ok(data={"created": created}, message=_("{0} task(s) opened").format(len(created)))


@frappe.whitelist()
def summary(property=None, project=None):
    """Counts for a maintenance board: open, in progress, overdue, due this
    week, completed this month."""
    base.require_user()
    filters = []
    if property:
        filters.append(["property", "=", property])
    if project:
        filters.append(["project", "=", project])
    rows = frappe.get_list(TASK, filters=filters, fields=["status", "scheduled_date", "completed_on"],
                           limit_page_length=0)
    now, week = today(), add_days(today(), 7)
    month = now[:7]
    live = [r for r in rows if r.status in ("Open", "In Progress")]
    return ok(
        data={
            "open": sum(1 for r in live if r.status == "Open"),
            "in_progress": sum(1 for r in live if r.status == "In Progress"),
            "overdue": sum(1 for r in live if str(r.scheduled_date) < now),
            "due_this_week": sum(1 for r in live if now <= str(r.scheduled_date) <= week),
            "completed_this_month": sum(1 for r in rows if r.status == "Completed"
                                        and str(r.completed_on or "")[:7] == month),
            "lead_days": frappe.db.get_single_value("Property Core Settings", "maintenance_task_lead_days"),
            "proof_required": proof_required(),
        }
    )


# --------------------------------------------------------------------------- #

def _decorate(rows):
    names = base.user_names([r.get("assigned_to") for r in rows])
    now = today()
    for row in rows:
        row["assigned_to_name"] = names.get(row.get("assigned_to"))
        row["overdue"] = row.get("status") in ("Open", "In Progress") and str(row.get("scheduled_date")) < now


def _brief(name):
    row = frappe.db.get_value(TASK, name, ["name", "status", "progress", "completed_on", "last_update_on"],
                              as_dict=True)
    row["proof_count"] = len(proof_files(name))
    return base.serialize(row)


def _multipart():
    return bool(frappe.request and getattr(frappe.request, "files", None) and frappe.request.files.getlist("file"))


def _attach_all(doctype, docname, files=None, filename=None, content=None):
    """Every proof file in the request, as private attachments on the record."""
    incoming = []
    if _multipart():
        for upload in frappe.request.files.getlist("file"):
            incoming.append((upload.filename, upload.stream.read()))
    for row in base.parse(files, default=[]) or []:
        incoming.append((row.get("filename"), _b64(row.get("content"))))
    if content:
        incoming.append((filename, _b64(content)))

    out = []
    for fname, data in incoming:
        if not fname:
            frappe.throw(_("Every file needs a filename"), frappe.MandatoryError)
        if len(data) > MAX_BYTES:
            frappe.throw(_("{0} is larger than {1} MB").format(fname, MAX_BYTES // (1024 * 1024)))
        f = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": fname,
                "attached_to_doctype": doctype,
                "attached_to_name": docname,
                "is_private": 1,
                "content": data,
            }
        )
        f.save(ignore_permissions=True)
        out.append({"name": f.name, "file_name": f.file_name, "file_url": f.file_url})
    return out


def _b64(content):
    content = content or ""
    if content.startswith("data:") and "," in content[:200]:
        content = content.split(",", 1)[1]
    return base64.b64decode(content)
