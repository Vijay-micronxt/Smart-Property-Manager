"""The reporting hierarchy, and how each person on it is doing.

JD's floor is a tree: an admin over sales heads, a head over managers, a
manager over executives. The app needs that tree twice -- to fill the "assign
to" picker with only the people this login may hand work to, and to draw a
manager's team view.
"""

import frappe
from frappe.utils import flt

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_core.crm import scope


@frappe.whitelist()
def my_team():
    """The people under this login, flat and nested."""
    user = base.require_user()
    members = scope.team_members(user)
    names = base.user_names(members + [user])

    return ok(
        data={
            "user": user,
            "scope": scope.scope_level(user),
            "members": [{"user": u, "full_name": names.get(u)} for u in members],
            "tree": scope.team_tree(user),
        }
    )


@frappe.whitelist()
def assignable_users():
    """Who this login may assign a lead or follow-up to: themselves and their
    team. An admin gets everyone holding a property role."""
    user = base.require_user()

    if scope.scope_level(user) == scope.ALL:
        users = _users_with_property_roles()
    else:
        users = scope.visible_users(user)

    names = base.user_names(users)
    return ok(
        data=[{"user": u, "full_name": names.get(u) or u} for u in sorted(users) if u != "Guest"]
    )


@frappe.whitelist()
def performance(from_date=None, to_date=None):
    """Leads / opportunities / bookings per person, for the people this login
    can see. Values come off the booking, so it is money agreed, not forecast.
    """
    user = base.require_user()
    users = scope.visible_users(user)
    if scope.scope_level(user) == scope.ALL:
        users = _users_with_property_roles()

    names = base.user_names(users)
    rows = []
    for member in sorted(users):
        rows.append(
            {
                "user": member,
                "full_name": names.get(member) or member,
                "leads": _count("Lead", "lead_owner", member, "creation", from_date, to_date),
                "opportunities": _count(
                    "Opportunity", "opportunity_owner", member, "creation", from_date, to_date
                ),
                **_booking_numbers(member, from_date, to_date),
                "open_follow_ups": _count(
                    "Property Follow Up",
                    "assigned_to",
                    member,
                    None,
                    None,
                    None,
                    extra={"status": "Open"},
                ),
            }
        )

    rows.sort(key=lambda r: r["booked_value"], reverse=True)
    return ok(data={"from_date": from_date, "to_date": to_date, "rows": rows})


def _users_with_property_roles():
    roles = list(scope.ADMIN_ROLES) + list(scope.MANAGER_ROLES) + list(scope.EXECUTIVE_ROLES)
    users = frappe.get_list(
        "Has Role",
        filters={"role": ["in", roles], "parenttype": "User"},
        pluck="parent",
        ignore_permissions=True,
    )
    enabled = frappe.get_list(
        "User",
        filters={"name": ["in", list(set(users)) or [""]], "enabled": 1},
        pluck="name",
        ignore_permissions=True,
    )
    return sorted(set(enabled))


def _count(doctype, field, user, date_field=None, from_date=None, to_date=None, extra=None):
    filters = {field: user}
    if extra:
        filters.update(extra)
    filters = [[key, "=", value] for key, value in filters.items()]
    if date_field:
        base.date_range(filters, date_field, from_date, to_date)
    rows = frappe.get_list(doctype, filters=filters, fields=["count(name) as total"])
    return rows[0].total if rows else 0


def _booking_numbers(user, from_date, to_date):
    """A booking is credited to whoever raised it."""
    filters = [["owner", "=", user], ["docstatus", "<", 2]]
    base.date_range(filters, "booking_date", from_date, to_date)
    rows = frappe.get_list(
        "Property Booking", filters=filters, fields=["name", "total_price", "docstatus"]
    )
    return {
        "bookings": len(rows),
        "confirmed_bookings": len([r for r in rows if r.docstatus == 1]),
        "booked_value": flt(sum(flt(r.total_price) for r in rows if r.docstatus == 1), 2),
    }
