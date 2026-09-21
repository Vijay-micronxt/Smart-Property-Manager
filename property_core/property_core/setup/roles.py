"""The three roles a real-estate sales floor actually needs, and what each may
touch.

Frappe auto-creates a Role for every role named in a DocType's permissions,
but it never grants anything on ERPNext's own doctypes (Lead, Opportunity,
Customer, Project) and it never assigns a role to a user. So a fresh site ends
up with a Property Manager who cannot open a Lead, and a sales executive with
no role at all -- which is exactly the "page not found / nothing visible"
complaint from the desk.

This module is idempotent and runs on every migrate (see ``after_migrate`` in
hooks.py). It only ever *adds* permissions; nothing is stripped, so a site that
has tuned its own Custom DocPerms keeps them.

Row-level visibility (who sees whose leads) is not here -- that is
``property_core.property_core.crm.scope``.
"""

import frappe

ADMIN = "Property Manager"
MANAGER = "Property Sales Manager"
EXECUTIVE = "Property Sales Executive"

ROLES = {
    ADMIN: "Full access to every property, booking and pipeline in the company.",
    MANAGER: "Sees and works their own pipeline plus everyone reporting to them.",
    EXECUTIVE: "Sees and works only the leads, opportunities and bookings they own.",
}

READ = {"read": 1, "report": 1, "export": 1}
WRITE = {**READ, "write": 1, "create": 1}
FULL = {**WRITE, "delete": 1, "submit": 1, "cancel": 1, "amend": 1}
WRITE_SUBMIT = {**WRITE, "submit": 1, "cancel": 1, "amend": 1}

#: doctype -> role -> permission flags
PERMISSIONS = {
    # --- the funnel ------------------------------------------------------- #
    "Lead": {ADMIN: FULL, MANAGER: {**WRITE, "delete": 1}, EXECUTIVE: WRITE},
    "Opportunity": {ADMIN: FULL, MANAGER: {**WRITE, "delete": 1}, EXECUTIVE: WRITE},
    "Property Follow Up": {ADMIN: FULL, MANAGER: {**WRITE, "delete": 1}, EXECUTIVE: WRITE},
    "Property Booking": {ADMIN: FULL, MANAGER: WRITE_SUBMIT, EXECUTIVE: WRITE},
    "Customer": {MANAGER: WRITE, EXECUTIVE: WRITE},
    "Contact": {MANAGER: WRITE, EXECUTIVE: WRITE},
    "Address": {MANAGER: WRITE, EXECUTIVE: WRITE},
    "Communication": {MANAGER: WRITE, EXECUTIVE: WRITE},
    "ToDo": {MANAGER: WRITE, EXECUTIVE: WRITE},
    # --- inventory the funnel reads but must not edit --------------------- #
    "Project": {MANAGER: READ, EXECUTIVE: READ},
    "Property": {MANAGER: READ, EXECUTIVE: READ},
    "Property Unit": {MANAGER: READ, EXECUTIVE: READ},
    "Payment Plan Template": {MANAGER: READ, EXECUTIVE: READ},
    # --- money, read-only for sales --------------------------------------- #
    "Payment Plan": {MANAGER: READ, EXECUTIVE: READ},
    "Sales Invoice": {MANAGER: READ, EXECUTIVE: READ},
    "Payment Entry": {MANAGER: READ, EXECUTIVE: READ},
}

#: Property Manager runs the whole property side, so it also needs the
#: ERPNext-native masters the funnel leans on.
ADMIN_EXTRA = {
    "Customer": FULL,
    "Contact": FULL,
    "Address": FULL,
    "Project": WRITE,
    "Sales Invoice": READ,
    "Payment Entry": READ,
}


def sync_property_roles():
    """Create the roles and grant what each one needs. Safe to re-run."""
    for role, description in ROLES.items():
        ensure_role(role, description)

    grants = {}
    for doctype, by_role in PERMISSIONS.items():
        grants.setdefault(doctype, {}).update(by_role)
    for doctype, flags in ADMIN_EXTRA.items():
        grants.setdefault(doctype, {})[ADMIN] = flags

    for doctype, by_role in grants.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for role, flags in by_role.items():
            grant(doctype, role, flags)

    frappe.db.commit()


def ensure_role(role, description=None):
    if frappe.db.exists("Role", role):
        # An existing role may have been created without desk access by a
        # DocType permission sync; sales staff log into the desk.
        if not frappe.db.get_value("Role", role, "desk_access"):
            frappe.db.set_value("Role", role, "desk_access", 1)
        return role

    doc = frappe.new_doc("Role")
    doc.role_name = role
    doc.desk_access = 1
    doc.search_bar = 1
    doc.notifications = 1
    doc.list_sidebar = 1
    doc.form_sidebar = 1
    doc.timeline = 1
    doc.dashboard = 1
    if description:
        doc.description = description
    doc.insert(ignore_permissions=True)
    return role


def grant(doctype, role, flags):
    """Add the role to the doctype's permissions and switch the given flags on."""
    from frappe.permissions import add_permission, update_permission_property

    try:
        add_permission(doctype, role, 0)
    except frappe.DoesNotExistError:
        return

    for ptype, value in flags.items():
        current = frappe.db.get_value(
            "Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}, ptype
        )
        if current == value:
            continue
        try:
            update_permission_property(doctype, role, 0, ptype, value, validate=False)
        except Exception:
            # Submit/cancel/amend on a non-submittable doctype throws; the rest
            # of the grant is still worth keeping.
            continue


def assign_role(user, role):
    """Give a user one of the property roles -- the step Frappe never does."""
    ensure_role(role)
    user_doc = frappe.get_doc("User", user)
    if role not in [r.role for r in user_doc.roles]:
        user_doc.append("roles", {"role": role})
        user_doc.save(ignore_permissions=True)
    return {"user": user, "roles": [r.role for r in user_doc.roles]}
