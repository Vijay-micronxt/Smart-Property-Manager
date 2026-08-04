"""Who the logged-in customer is, and their contact details."""

import frappe

from property_core.api.portal.base import customer_units, get_customer, serialize
from property_core.api.utils import ok


@frappe.whitelist()
def me():
    """Customer identity + contact + a count of what they hold."""
    customer = get_customer()
    user = frappe.session.user

    doc = frappe.db.get_value(
        "Customer",
        customer,
        ["name", "customer_name", "customer_type", "customer_group", "territory",
         "mobile_no", "email_id", "image"],
        as_dict=True,
    ) or {}

    contact_name = frappe.db.get_value("Contact", {"email_id": user}, "name")
    contact = {}
    if contact_name:
        contact = frappe.db.get_value(
            "Contact", contact_name,
            ["first_name", "last_name", "email_id", "mobile_no", "phone"],
            as_dict=True,
        ) or {}

    units = customer_units(customer)

    return ok(data=serialize({
        "user": user,
        "full_name": frappe.db.get_value("User", user, "full_name") or user,
        "customer": doc,
        "contact": contact,
        "counts": {
            "units": len(units),
            "bookings": frappe.db.count(
                "Property Booking", {"customer": customer, "docstatus": ["<", 2]}
            ),
            "open_issues": frappe.db.count(
                "Issue", {"customer": customer, "status": ["not in", ["Closed", "Resolved"]]}
            ),
        },
    }))


@frappe.whitelist()
def update_contact(mobile_no=None, phone=None, first_name=None, last_name=None):
    """Let the customer correct their own contact row. Email is never editable
    here -- it is the login identity."""
    get_customer()

    contact_name = frappe.db.get_value("Contact", {"email_id": frappe.session.user}, "name")
    if not contact_name:
        frappe.throw(frappe._("No contact record is linked to your login."))

    contact = frappe.get_doc("Contact", contact_name)
    for fieldname, value in (
        ("mobile_no", mobile_no), ("phone", phone),
        ("first_name", first_name), ("last_name", last_name),
    ):
        if value is not None and str(value).strip():
            setattr(contact, fieldname, str(value).strip())

    contact.flags.ignore_permissions = True
    contact.save(ignore_permissions=True)

    return ok(message=frappe._("Contact updated"), data={"contact": contact.name})
