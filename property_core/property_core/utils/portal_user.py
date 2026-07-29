import frappe


def ensure_portal_user(customer):
    """Give the Customer portal login access if they don't already have it.
    Wrapped in try/except by the caller -- a missing contact email or a mail
    server hiccup should never block whatever triggered this (e.g. a booking).
    """
    existing = frappe.db.get_value("Portal User", {"parenttype": "Customer", "parent": customer}, "name")
    if existing:
        return

    email = None
    mobile = None
    contact = frappe.db.get_value("Customer", customer, "customer_primary_contact")
    if not contact:
        contact = frappe.db.get_value(
            "Dynamic Link",
            {"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
            "parent",
        )
    if contact:
        email = frappe.db.get_value("Contact", contact, "email_id")
        mobile = frappe.db.get_value("Contact", contact, "mobile_no")

    if not email:
        return

    email = email.strip().lower()
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({
            "doctype": "User",
            "email": email,
            "first_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
            "mobile_no": mobile,
            "user_type": "Website User",
            "send_welcome_email": 1,
            "roles": [{"role": "Customer"}],
        })
        user.flags.ignore_permissions = True
        user.insert(ignore_permissions=True)
    elif mobile and not frappe.db.get_value("User", email, "mobile_no"):
        frappe.db.set_value("User", email, "mobile_no", mobile)

    link = frappe.get_doc({
        "doctype": "Portal User",
        "parenttype": "Customer",
        "parent": customer,
        "parentfield": "portal_users",
        "user": email,
    })
    link.flags.ignore_permissions = True
    link.insert(ignore_permissions=True)
