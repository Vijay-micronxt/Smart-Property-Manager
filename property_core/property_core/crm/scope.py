"""Who is allowed to see whose pipeline.

Every real-estate sales floor runs on the same three tiers, and JD is no
exception:

    * **Admin**          -- sees the whole company. Roles: Administrator,
      System Manager, Super Admin, Property Manager.
    * **Team manager**   -- sees their own work plus everyone under them in the
      reporting chain. Role: *Property Sales Manager*.
    * **Sales executive** -- sees only what they own or were assigned. Role:
      *Property Sales Executive* (and ERPNext's stock *Sales User*).

The reporting chain is the Employee tree (``Employee.reports_to``), because
that is what JD already maintains -- on live, ``hema`` reports to ``cgotur``
who reports to ``sales@jdhomes.co.in``. The tree is walked to the **full
depth**: a head of sales sees their managers' teams too, not just their direct
reports. The older Lead-only query stopped at one level and quietly hid
grandchildren's leads from the people accountable for them.

Everything here is used twice: by ``permission_query_conditions`` /
``has_permission`` so the desk and ``frappe.get_all`` obey it, and by the CRM
API in ``property_core.api.crm`` so the frontend gets the same rows without
re-implementing the rule.
"""

import frappe

from property_core.property_core.crm.lead_fields import RESTRICTED_STATUSES

ADMIN_ROLES = ("Super Admin", "System Manager", "Property Manager")
MANAGER_ROLES = ("Property Sales Manager", "Sales Manager", "Sales Master Manager")
EXECUTIVE_ROLES = ("Property Sales Executive", "Sales User")

#: kept for the old lead_permissions entry point
UNRESTRICTED_ROLES = ADMIN_ROLES

ALL = "all"
TEAM = "team"
OWN = "own"

#: Doctypes this module scopes, and the fields that count as "ownership" on
#: each. ``assign`` means the ToDo/_assign trail is honoured as well.
OWNER_FIELDS = {
    "Lead": ("lead_owner", "owner", "custom_follow_up_owner"),
    "Opportunity": ("opportunity_owner", "owner"),
    "Property Booking": ("owner",),
    "Property Follow Up": ("assigned_to", "owner", "completed_by"),
}


# --------------------------------------------------------------------------- #
# level + visible users
# --------------------------------------------------------------------------- #

def scope_level(user=None):
    """``all`` / ``team`` / ``own`` for this user."""
    user = user or frappe.session.user
    if user == "Administrator":
        return ALL

    roles = set(frappe.get_roles(user))
    if roles.intersection(ADMIN_ROLES):
        return ALL
    if roles.intersection(MANAGER_ROLES):
        return TEAM
    return OWN


def visible_users(user=None):
    """Users whose records this user may see -- themselves plus, for a manager,
    everyone below them in the Employee tree."""
    user = user or frappe.session.user
    cached = _cache().get(("visible_users", user))
    if cached is not None:
        return cached

    users = {user}
    if scope_level(user) != OWN:
        users.update(_reporting_subtree(user))

    result = sorted(u for u in users if u)
    _cache()[("visible_users", user)] = result
    return result


def team_members(user=None):
    """Just the people under this user -- the user themselves excluded."""
    user = user or frappe.session.user
    return [u for u in visible_users(user) if u != user]


def team_tree(user=None):
    """The reporting chain below this user as nested dicts, for the frontend's
    team switcher. Empty list for an executive."""
    user = user or frappe.session.user
    employee = _employee_of(user)
    if not employee or scope_level(user) == OWN:
        return []
    return _children_of(employee)


def _children_of(employee):
    rows = frappe.get_all(
        "Employee",
        filters={"reports_to": employee, "status": "Active"},
        fields=["name", "employee_name", "user_id", "designation"],
        ignore_permissions=True,
    )
    return [
        {
            "employee": row.name,
            "employee_name": row.employee_name,
            "user": row.user_id,
            "designation": row.designation,
            "reports": _children_of(row.name),
        }
        for row in rows
    ]


def _reporting_subtree(user):
    """Every ``user_id`` below this user in the Employee tree, at any depth."""
    employee = _employee_of(user)
    if not employee:
        return set()

    users = set()
    frontier = [employee]
    seen = {employee}
    while frontier:
        rows = frappe.get_all(
            "Employee",
            filters={"reports_to": ["in", frontier]},
            fields=["name", "user_id"],
            ignore_permissions=True,
        )
        frontier = []
        for row in rows:
            if row.name in seen:
                # A cycle in reports_to would otherwise spin here forever.
                continue
            seen.add(row.name)
            frontier.append(row.name)
            if row.user_id:
                users.add(row.user_id)

    return users


def _employee_of(user):
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name") or (
        frappe.db.get_value("Employee", {"user_id": user}, "name")
    )


def _cache():
    if not hasattr(frappe.local, "property_core_scope"):
        frappe.local.property_core_scope = {}
    return frappe.local.property_core_scope


# --------------------------------------------------------------------------- #
# SQL conditions -- used by permission_query_conditions
# --------------------------------------------------------------------------- #

def ownership_condition(doctype, user=None):
    """SQL that keeps a listing inside the user's own (or team's) records.

    Returns ``""`` when the user may see everything.
    """
    user = user or frappe.session.user
    if scope_level(user) == ALL:
        return ""

    users = visible_users(user)
    user_list = ", ".join(frappe.db.escape(u) for u in users)
    table = f"`tab{doctype}`"

    clauses = [f"{table}.`{field}` IN ({user_list})" for field in OWNER_FIELDS.get(doctype, ("owner",))]
    clauses.append(
        f"""{table}.`name` IN (
            SELECT `reference_name` FROM `tabToDo`
            WHERE `reference_type` = {frappe.db.escape(doctype)}
              AND `allocated_to` IN ({user_list})
              AND `status` IN ('Open', 'Pending')
        )"""
    )

    return "(" + " OR ".join(clauses) + ")"


def get_lead_conditions(user=None):
    """Lead also hides the dead statuses from everyone but an admin, so the
    working queue stays the live pipeline."""
    user = user or frappe.session.user
    ownership = ownership_condition("Lead", user)
    if not ownership:
        return ""

    dead = " AND ".join(
        f"IFNULL(`tabLead`.`custom_lead_status`, '') != {frappe.db.escape(status)}"
        for status in RESTRICTED_STATUSES
    )
    return f"({ownership} AND ({dead}))"


def get_opportunity_conditions(user=None):
    return ownership_condition("Opportunity", user)


def get_booking_conditions(user=None):
    """A booking is visible to whoever raised it, whoever it is assigned to,
    and -- because the deal is credited to them -- to the sales person on it."""
    user = user or frappe.session.user
    base = ownership_condition("Property Booking", user)
    if not base:
        return ""

    persons = sales_persons_for(visible_users(user))
    if persons:
        person_list = ", ".join(frappe.db.escape(p) for p in persons)
        base = base[:-1] + f" OR `tabProperty Booking`.`sales_person` IN ({person_list}))"

    # A booking that came out of an opportunity the user can see should stay
    # visible even if someone else keyed it in.
    opportunity = get_opportunity_conditions(user)
    if opportunity:
        base = (
            base[:-1]
            + f""" OR `tabProperty Booking`.`opportunity` IN (
                SELECT `name` FROM `tabOpportunity` WHERE {opportunity}
            ))"""
        )
    return base


def get_follow_up_conditions(user=None):
    return ownership_condition("Property Follow Up", user)


def sales_persons_for(users):
    """Sales Person records tied to these users through their Employee."""
    if not users:
        return []
    employees = frappe.get_all(
        "Employee", filters={"user_id": ["in", users]}, pluck="name", ignore_permissions=True
    )
    if not employees:
        return []
    return frappe.get_all(
        "Sales Person",
        filters={"employee": ["in", employees]},
        pluck="name",
        ignore_permissions=True,
    )


# --------------------------------------------------------------------------- #
# document-level checks -- used by has_permission
# --------------------------------------------------------------------------- #

def has_document_permission(doc, ptype=None, user=None):
    user = user or frappe.session.user
    if scope_level(user) == ALL:
        return True
    if user == "Administrator":
        return True

    users = set(visible_users(user))
    for field in OWNER_FIELDS.get(doc.doctype, ("owner",)):
        if doc.get(field) and doc.get(field) in users:
            return True

    if doc.doctype == "Property Booking":
        if doc.get("sales_person") and doc.sales_person in sales_persons_for(users):
            return True
        if doc.get("opportunity"):
            opportunity_owner = frappe.db.get_value(
                "Opportunity", doc.opportunity, ["opportunity_owner", "owner"], as_dict=True
            )
            if opportunity_owner and (
                opportunity_owner.opportunity_owner in users or opportunity_owner.owner in users
            ):
                return True

    assigned = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "allocated_to": ["in", list(users)],
            "status": ["in", ["Open", "Pending"]],
        },
        limit=1,
        ignore_permissions=True,
    )
    return bool(assigned)


def has_lead_permission(doc, ptype=None, user=None):
    return has_document_permission(doc, ptype, user)


def has_opportunity_permission(doc, ptype=None, user=None):
    return has_document_permission(doc, ptype, user)


def has_booking_permission(doc, ptype=None, user=None):
    return has_document_permission(doc, ptype, user)


def has_follow_up_permission(doc, ptype=None, user=None):
    return has_document_permission(doc, ptype, user)


# --------------------------------------------------------------------------- #
# helpers for the API layer
# --------------------------------------------------------------------------- #

def owner_filters(doctype, user=None):
    """The same rule as a list of frappe filters, for API calls that ask for
    "mine only" explicitly. ``None`` means no restriction."""
    user = user or frappe.session.user
    if scope_level(user) == ALL:
        return None

    users = visible_users(user)
    fields = OWNER_FIELDS.get(doctype, ("owner",))
    return [[doctype, fields[0], "in", users]]


def describe(user=None):
    """What the frontend needs to draw the right screen for this login."""
    user = user or frappe.session.user
    level = scope_level(user)
    return {
        "user": user,
        "scope": level,
        "is_admin": level == ALL,
        "is_manager": level == TEAM,
        "team": team_members(user) if level != OWN else [],
        "team_tree": team_tree(user),
    }
