"""
Whitelisted APIs for a logged-in customer. Website users have no doctype
permissions, so every function here resolves and scopes to the calling
customer itself -- that resolution is the actual security boundary.
"""

import frappe
from frappe.utils import getdate, today, date_diff


def _get_customer_for_session():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(frappe._("Please login"))

    customer = frappe.db.get_value("Portal User", {"user": user, "parenttype": "Customer"}, "parent")
    if not customer:
        contact = frappe.db.get_value("Contact", {"email_id": user}, "name")
        if contact:
            customer = frappe.db.get_value(
                "Dynamic Link",
                {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
                "link_name",
            )
    if not customer:
        frappe.throw(frappe._("No customer account is linked to your login. Please contact our team."))

    return customer


@frappe.whitelist()
def raise_issue(subject, description=None, property_unit=None):
    customer = _get_customer_for_session()

    subject = (subject or "").strip()
    if not subject:
        frappe.throw(frappe._("Subject is required"))

    if property_unit:
        owns_unit = frappe.db.exists(
            "Property Booking",
            {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
        ) or frappe.db.exists(
            "Property Allocation",
            {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
        )
        if not owns_unit:
            frappe.throw(frappe._("Selected unit does not belong to your account"))

    issue = frappe.get_doc({
        "doctype": "Issue",
        "subject": subject,
        "description": description or subject,
        "raised_by": frappe.session.user,
        "customer": customer,
        "property_unit": property_unit or None,
    })
    issue.flags.ignore_permissions = True
    issue.insert(ignore_permissions=True)

    return {"ok": 1, "issue": issue.name}


@frappe.whitelist()
def customer_portal_get():
    customer = _get_customer_for_session()
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    today_date = getdate(today())

    bookings = []
    for booking in frappe.get_all(
        "Property Booking",
        filters={"customer": customer, "docstatus": ["<", 2]},
        fields=["name", "property_unit", "booking_date", "booking_status", "booking_amount"],
        order_by="creation desc",
    ):
        plans = frappe.get_all(
            "Payment Plan",
            filters={"booking": booking.name},
            fields=["name", "milestone", "due_date", "amount", "payment_status", "invoice"],
            order_by="due_date asc",
        )
        for plan in plans:
            if plan.payment_status == "Paid":
                plan["status"] = "Paid"
            elif plan.due_date and getdate(plan.due_date) < today_date:
                plan["status"] = "Overdue"
            elif plan.due_date and date_diff(plan.due_date, today_date) <= 7:
                plan["status"] = "Due Soon"
            else:
                plan["status"] = "Upcoming"
            plan["due_date"] = str(plan.due_date) if plan.due_date else None

        bookings.append({
            "name": booking.name,
            "property_unit": booking.property_unit,
            "booking_date": str(booking.booking_date) if booking.booking_date else None,
            "booking_status": booking.booking_status,
            "booking_amount": booking.booking_amount,
            "payment_plan": plans,
        })

    units = frappe.get_all(
        "Property Unit",
        filters={"customer": customer},
        fields=["name", "property", "unit_number", "unit_type", "area", "base_price", "availability_status"],
    )

    agreements = frappe.get_all(
        "Property Agreement",
        filters={"customer": customer},
        fields=["name", "agreement_type", "agreement_status", "start_date", "end_date", "document_attachment"],
    )

    issues = frappe.get_all(
        "Issue",
        filters={"customer": customer},
        fields=["name", "subject", "status", "opening_date", "property_unit"],
        order_by="creation desc",
        limit_page_length=50,
    )

    return {
        "customer": {"name": customer, "customer_name": customer_name},
        "bookings": bookings,
        "units": units,
        "agreements": agreements,
        "issues": issues,
    }
