"""Complaints and tickets: raise one, track it, talk on it."""

import frappe

from property_core.api.portal.base import (
    as_int,
    assert_doc,
    assert_unit,
    get_customer,
    get_list,
    serialize,
)
from property_core.api.utils import ok

OPEN_STATUSES = ["Open", "Replied", "Paused"]


@frappe.whitelist()
def issues(property_unit=None, status=None, limit=50):
    """The customer's tickets with the work raised against each."""
    customer = get_customer()

    filters = {"customer": customer}
    if property_unit:
        assert_unit(customer, property_unit)
        filters["property_unit"] = property_unit
    if status == "Open":
        filters["status"] = ["in", OPEN_STATUSES]
    elif status:
        filters["status"] = status

    rows = get_list(
        "Issue", filters, order_by="creation desc", limit_page_length=as_int(limit, 50)
    )
    for row in rows:
        row["work_orders"] = get_list("Work Order", {"issue": row["name"]}, order_by="creation desc")
        if row.get("property_unit"):
            row["unit_number"] = frappe.db.get_value(
                "Property Unit", row["property_unit"], "unit_number"
            )

    return ok(data={
        "issues": rows,
        "open_count": sum(1 for r in rows if r.get("status") in OPEN_STATUSES),
        "total": len(rows),
    })


@frappe.whitelist()
def issue(issue):
    """One ticket in full: work orders and the conversation on it."""
    customer = get_customer()
    assert_doc(customer, "Issue", issue)

    rows = get_list("Issue", {"name": issue})
    row = rows[0]
    row["work_orders"] = get_list("Work Order", {"issue": issue}, order_by="creation desc")
    row["comments"] = serialize(frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": "Issue",
            "reference_name": issue,
            "comment_type": "Comment",
        },
        fields=["name", "comment_email", "comment_by", "content", "creation"],
        order_by="creation asc",
    ))
    if row.get("property_unit"):
        row["unit_number"] = frappe.db.get_value(
            "Property Unit", row["property_unit"], "unit_number"
        )

    return ok(data=row)


@frappe.whitelist()
def raise_issue(subject, description=None, property_unit=None, priority=None):
    """Open a ticket. The unit, if given, must be the customer's own."""
    customer = get_customer()

    subject = (subject or "").strip()
    if not subject:
        frappe.throw(frappe._("Subject is required"))

    if property_unit:
        assert_unit(customer, property_unit)

    doc = frappe.get_doc({
        "doctype": "Issue",
        "subject": subject,
        "description": description or subject,
        "raised_by": frappe.session.user,
        "customer": customer,
        "property_unit": property_unit or None,
    })
    if priority and frappe.db.exists("Issue Priority", priority):
        doc.priority = priority

    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)

    return ok(
        message=frappe._("Ticket raised. Our team will get back to you."),
        data={"issue": doc.name, "status": doc.status},
    )


@frappe.whitelist()
def add_comment(issue, message):
    """Reply on the customer's own ticket."""
    customer = get_customer()
    assert_doc(customer, "Issue", issue)

    message = (message or "").strip()
    if not message:
        frappe.throw(frappe._("Message is required"))

    comment = frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Comment",
        "reference_doctype": "Issue",
        "reference_name": issue,
        "content": message,
        "comment_email": frappe.session.user,
        "comment_by": frappe.db.get_value("User", frappe.session.user, "full_name"),
    })
    comment.insert(ignore_permissions=True)

    return ok(message=frappe._("Comment added"), data={"comment": comment.name})
