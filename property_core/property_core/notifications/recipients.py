"""Work out who to message and on which address."""

import frappe
from frappe.utils import cstr


def for_customer(customer):
    """Best available email + mobile for a Customer.

    Order of preference: the primary Contact, then any linked Contact, then the
    denormalised fields on Customer itself. Returns a dict the dispatcher
    understands; missing keys become Skipped log rows, not errors.
    """
    if not customer:
        return {}

    row = frappe.db.get_value(
        "Customer",
        customer,
        ["customer_name", "customer_primary_contact", "mobile_no", "email_id"],
        as_dict=True,
    )
    if not row:
        return {}

    email = row.email_id
    mobile = row.mobile_no

    contact_name = row.customer_primary_contact or _first_linked_contact(customer)
    if contact_name and not (email and mobile):
        contact = frappe.db.get_value(
            "Contact", contact_name, ["email_id", "mobile_no", "phone"], as_dict=True
        )
        if contact:
            email = email or contact.email_id
            mobile = mobile or contact.mobile_no or contact.phone

    return {
        "name": row.customer_name or customer,
        "email": email,
        "mobile": mobile,
        "party_type": "Customer",
        "party": customer,
    }


def _first_linked_contact(customer):
    rows = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Customer",
            "link_name": customer,
            "parenttype": "Contact",
        },
        pluck="parent",
        limit=1,
    )
    return rows[0] if rows else None


def for_user(user):
    """Email + mobile for a System/Sales user -- used for internal reminders."""
    if not user:
        return {}

    row = frappe.db.get_value(
        "User", user, ["full_name", "email", "mobile_no", "phone", "enabled"], as_dict=True
    )
    if not row or not row.enabled:
        return {}

    return {
        "name": row.full_name or user,
        "email": row.email or user,
        "mobile": row.mobile_no or row.phone,
        "party_type": "User",
        "party": user,
    }


def for_lead_owner(lead):
    """Whoever should chase this Lead.

    Explicit follow-up owner wins, then the standard lead_owner, then the first
    ToDo assignee, then the document owner -- so a lead reassigned only through
    the assignment sidebar still reaches the right person.
    """
    candidate = (
        lead.get("custom_follow_up_owner")
        or lead.get("lead_owner")
        or _first_assignee(lead)
        or lead.get("owner")
    )
    return for_user(candidate)


def _first_assignee(lead):
    assignees = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": lead.doctype,
            "reference_name": lead.name,
            "status": ["!=", "Cancelled"],
        },
        pluck="allocated_to",
        order_by="creation desc",
        limit=1,
    )
    return assignees[0] if assignees else None


def property_unit_label(unit_name):
    """'A-101 (Green Acres)' for message bodies, or empty string."""
    if not unit_name:
        return ""
    row = frappe.db.get_value("Property Unit", unit_name, ["unit_number", "property"], as_dict=True)
    if not row:
        return ""
    return "{} ({})".format(row.unit_number, row.property) if row.property else cstr(row.unit_number)
