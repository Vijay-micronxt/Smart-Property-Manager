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
        # A Customer made straight from a Lead may carry the address and email
        # itself without a Contact ever being created.
        values = frappe.db.get_value(
            "Customer", customer, ["email_id", "mobile_no"], as_dict=True
        ) or {}
        email = values.get("email_id")
        mobile = mobile or values.get("mobile_no")

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
            "send_welcome_email": 1 if _can_send_welcome_mail() else 0,
            "roles": [{"role": "Customer"}],
        })
        user.flags.ignore_permissions = True
        user.insert(ignore_permissions=True)
        keep_as_website_user(email)
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


def _can_send_welcome_mail():
    """No default outgoing account means User.insert() dies inside the welcome
    mail and takes the whole portal user with it."""
    return bool(frappe.db.exists("Email Account", {"default_outgoing": 1, "enabled": 1}))


def keep_as_website_user(email):
    """Strip desk access from a portal login we just created.

    Frappe Drive hooks User.after_insert and appends its own "Drive User" role,
    which carries desk_access -- and Frappe promotes any user holding a
    desk-access role to System User. A customer who only needs the portal would
    otherwise end up with a desk login and a paid seat.

    Only ever called on a user this function created, so an existing staff
    account is never demoted.
    """
    desk_roles = frappe.get_all("Role", filters={"desk_access": 1}, pluck="name")
    if desk_roles:
        frappe.db.delete("Has Role", {"parent": email, "role": ["in", desk_roles]})

    frappe.db.set_value("User", email, "user_type", "Website User", update_modified=False)
