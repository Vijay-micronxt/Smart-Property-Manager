"""Login and "who am I" for the CRM frontend.

``/api/method/frappe.auth.get_logged_user`` is not callable on every Frappe
build -- JD live answers *"Function frappe.auth.get_logged_user is not
whitelisted"* -- and even where it works it returns a bare string, so the app
still has to make three more calls to learn the user's roles and what they may
see. ``whoami`` below answers all of it in one request.

Auth is the same token scheme the customer portal uses:

    POST /api/method/property_core.api.crm.session.login
         {"usr": "...", "pwd": "..."}
      -> {"data": {"api_key": "...", "api_secret": "...", ...}}

    every later call:
        Authorization: token <api_key>:<api_secret>

A browser session cookie works just as well -- nothing here requires the
token.
"""

import frappe

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_core.crm import scope
from property_core.property_core.setup.roles import ADMIN, EXECUTIVE, MANAGER


@frappe.whitelist(allow_guest=True)
def login(usr, pwd):
    """Authenticate a staff user and hand back an API token plus their scope."""
    try:
        login_manager = frappe.auth.LoginManager()
        login_manager.authenticate(user=usr, pwd=pwd)
        login_manager.post_login()
    except frappe.AuthenticationError:
        frappe.throw("Invalid email or password", frappe.AuthenticationError)

    from property_core.api.auth import get_token

    token = get_token()
    data = token.get("data", {})
    data.update(_profile(frappe.session.user))
    return ok(data=data)


@frappe.whitelist()
def whoami():
    """Everything the app needs to draw the right screen for this login."""
    user = base.require_user()
    return ok(data=_profile(user))


# The frontend asked for this name; keep both so either spelling works.
@frappe.whitelist()
def me():
    return whoami()


@frappe.whitelist()
def refresh_token():
    """New api_key/api_secret for the current session user."""
    base.require_user()
    from property_core.api.auth import get_token

    return get_token()


@frappe.whitelist()
def logout():
    frappe.local.login_manager.logout()
    frappe.db.commit()
    return ok(message="Logged out")


def _profile(user):
    info = frappe.db.get_value(
        "User", user, ["name", "full_name", "email", "user_image", "mobile_no", "time_zone"], as_dict=True
    ) or {}
    roles = frappe.get_roles(user)
    level = scope.scope_level(user)

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user},
        ["name", "employee_name", "designation", "department", "reports_to", "company"],
        as_dict=True,
    )

    return {
        **info,
        # ``user`` as well as ``name``: every other endpoint speaks of a user
        # id, and the frontend should not have to know that User.name is it.
        "user": user,
        "roles": roles,
        "scope": level,
        "is_admin": level == scope.ALL,
        "is_manager": level == scope.TEAM,
        "property_role": (
            ADMIN if level == scope.ALL else MANAGER if level == scope.TEAM else EXECUTIVE
        ),
        "employee": employee,
        "team": scope.team_members(user),
        "permissions": _permissions(),
        "defaults": {
            "company": frappe.defaults.get_user_default("Company"),
            "currency": frappe.db.get_default("currency"),
            "date_format": frappe.db.get_single_value("System Settings", "date_format"),
            "time_zone": frappe.db.get_single_value("System Settings", "time_zone"),
        },
    }


def _permissions():
    """Per-doctype can-do map, so the app hides buttons it would be refused."""
    out = {}
    for doctype in (
        "Lead",
        "Opportunity",
        "Property Follow Up",
        "Property Booking",
        "Customer",
        "Property",
        "Property Unit",
        "Project",
    ):
        if not frappe.db.exists("DocType", doctype):
            continue
        out[doctype] = {
            action: bool(frappe.has_permission(doctype, action))
            for action in ("read", "write", "create", "delete", "submit", "cancel")
        }
    return out
