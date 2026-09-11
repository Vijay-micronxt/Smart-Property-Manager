"""Row-level visibility on Lead, ported from JD's CRM Lead permission query.

Rules, unchanged from what the team runs today:
  * Administrator / Super Admin        -- everything
  * Employee with reports_to under them -- own leads + the team's
  * Everyone else                       -- only leads they own or are assigned

On top of that, anyone who is not Administrator/Super Admin has the dead
statuses (Junk, Duplicate, ...) filtered out of the list so the working queue
stays the live pipeline. Statuses are matched on ``custom_lead_status`` --
native ``status`` is derived and far too coarse for this.
"""

import frappe

from property_core.property_core.crm.lead_fields import RESTRICTED_STATUSES

UNRESTRICTED_ROLES = ("Super Admin", "System Manager")


def get_permission_query_conditions(user=None):
    user = user or frappe.session.user

    if user == "Administrator":
        return ""

    roles = frappe.get_roles(user)
    if any(role in roles for role in UNRESTRICTED_ROLES):
        return ""

    visible_users = _visible_users(user)
    user_list = ", ".join(frappe.db.escape(u) for u in visible_users)

    ownership = f"""(
        `tabLead`.`lead_owner` IN ({user_list})
        OR `tabLead`.`owner` IN ({user_list})
        OR `tabLead`.`custom_follow_up_owner` IN ({user_list})
        OR `tabLead`.`name` IN (
            SELECT `reference_name` FROM `tabToDo`
            WHERE `reference_type` = 'Lead'
              AND `allocated_to` IN ({user_list})
              AND `status` IN ('Open', 'Pending')
        )
    )"""

    dead = " AND ".join(
        f"IFNULL(`tabLead`.`custom_lead_status`, '') != {frappe.db.escape(status)}"
        for status in RESTRICTED_STATUSES
    )

    return f"({ownership} AND ({dead}))"


def _visible_users(user):
    """The user, plus everyone reporting to them if they are a supervisor."""
    users = {user}

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if employee:
        reports = frappe.get_all("Employee", filters={"reports_to": employee}, pluck="user_id")
        users.update(u for u in reports if u)

    return sorted(users)
