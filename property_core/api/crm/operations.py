"""After handover: complaints (ERPNext Issue) and the site work that answers
them (Work Order). What the Operations desk does, over JSON."""

import frappe
from frappe import _

from property_core.api.crm import base
from property_core.api.utils import ok

WORK_ORDER_FIELDS = [
    "name",
    "property_unit",
    "work_type",
    "status",
    "issue",
    "assigned_to",
    "vendor",
    "scheduled_date",
    "completed_date",
    "progress",
    "estimated_cost",
    "actual_cost",
    "sales_invoice",
    "modified",
]

WORK_ORDER_WRITABLE = {
    "property_unit",
    "work_type",
    "status",
    "issue",
    "assigned_to",
    "vendor",
    "scheduled_date",
    "completed_date",
    "progress",
    "description",
    "estimated_cost",
    "actual_cost",
    "notes",
}

ISSUE_FIELDS = ["name", "subject", "status", "priority", "customer", "raised_by", "opening_date", "modified"]
ISSUE_WRITABLE = {"subject", "status", "priority", "customer", "raised_by", "description", "issue_type", "property_unit"}


@frappe.whitelist()
def get_work_orders(property_unit=None, status=None, assigned_to=None, mine=None, search=None, page=1, page_size=20):
    user = base.require_user()
    conditions = []
    if property_unit:
        conditions.append(["property_unit", "=", property_unit])
    if status:
        values = base.parse(status, default=status)
        conditions.append(["status", "in", values if isinstance(values, list) else [values]])
    who = user if base.as_bool(mine) else assigned_to
    if who:
        conditions.append(["assigned_to", "=", who])
    return ok(
        data=base.listing(
            "Work Order",
            WORK_ORDER_FIELDS,
            extra_filters=conditions,
            search=search,
            search_fields=["name", "property_unit", "description"],
            order_by="modified desc",
            page=page,
            page_size=page_size,
        )
    )


@frappe.whitelist()
def get_work_order(name):
    return ok(data=base.doc_payload(base.read_doc("Work Order", name)))


@frappe.whitelist()
def create_work_order(data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WORK_ORDER_WRITABLE})
    doc = base.create_doc("Work Order", payload, WORK_ORDER_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Work order {0} created").format(doc.name))


@frappe.whitelist()
def update_work_order(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WORK_ORDER_WRITABLE})
    doc, changed = base.write_doc("Work Order", name, payload, WORK_ORDER_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def get_issues(customer=None, property_unit=None, status=None, search=None, page=1, page_size=20):
    base.require_user()
    conditions = []
    if customer:
        conditions.append(["customer", "=", customer])
    if property_unit and frappe.get_meta("Issue").has_field("property_unit"):
        conditions.append(["property_unit", "=", property_unit])
    if status:
        conditions.append(["status", "=", status])
    fields = ISSUE_FIELDS + (["property_unit"] if frappe.get_meta("Issue").has_field("property_unit") else [])
    return ok(
        data=base.listing(
            "Issue",
            fields,
            extra_filters=conditions,
            search=search,
            search_fields=["name", "subject"],
            order_by="modified desc",
            page=page,
            page_size=page_size,
        )
    )


@frappe.whitelist()
def get_issue(name):
    doc = base.read_doc("Issue", name)
    payload = base.doc_payload(doc)
    payload["work_orders"] = base.serialize(
        frappe.get_list("Work Order", filters={"issue": name}, fields=WORK_ORDER_FIELDS)
        if base.can_read("Work Order")
        else []
    )
    return ok(data=payload)


@frappe.whitelist()
def create_issue(data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in ISSUE_WRITABLE})
    doc = base.create_doc("Issue", payload, ISSUE_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Issue {0} created").format(doc.name))


@frappe.whitelist()
def update_issue(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in ISSUE_WRITABLE})
    doc, changed = base.write_doc("Issue", name, payload, ISSUE_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def options():
    base.require_user()
    wo = frappe.get_meta("Work Order") if frappe.db.exists("DocType", "Work Order") else None
    issue = frappe.get_meta("Issue")
    split = lambda meta, f: [o for o in ((meta.get_field(f).options if meta and meta.get_field(f) else "") or "").split("\n") if o]
    return ok(
        data={
            "work_order": {"statuses": split(wo, "status"), "types": split(wo, "work_type")},
            "issue": {
                "statuses": split(issue, "status"),
                "priorities": frappe.get_all("Issue Priority", pluck="name"),
                "types": frappe.get_all("Issue Type", pluck="name"),
            },
        }
    )
