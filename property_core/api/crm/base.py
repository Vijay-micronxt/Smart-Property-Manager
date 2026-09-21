"""Shared plumbing for the staff CRM API.

Unlike the customer portal (whose users hold no permissions at all and are
scoped by hand), staff logins are ordinary desk users. So everything here goes
through Frappe's permission engine on purpose: ``frappe.get_all`` applies the
row-level conditions from ``crm.scope`` by itself, and a document read is
checked with ``frappe.has_permission``. The API can therefore never show a
sales executive more than the desk would.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import cint

DATE_TYPES = (datetime.date, datetime.datetime, datetime.time, datetime.timedelta)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# --------------------------------------------------------------------------- #
# request plumbing
# --------------------------------------------------------------------------- #

def require_user():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please login"), frappe.AuthenticationError)
    return user


def parse(value, default=None):
    """Query-string arguments arrive as strings; dicts and lists as JSON."""
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return frappe.parse_json(value)
    except Exception:
        return default


def as_bool(value, default=False):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def serialize(row):
    """Dates to ISO strings so JSON clients never see Frappe date objects."""
    if isinstance(row, list):
        return [serialize(r) for r in row]
    if not isinstance(row, dict):
        return row
    for key, value in row.items():
        if isinstance(value, DATE_TYPES):
            row[key] = str(value)
        elif isinstance(value, (dict, list)):
            row[key] = serialize(value)
    return row


def page_args(page=1, page_size=DEFAULT_PAGE_SIZE):
    page = max(cint(page) or 1, 1)
    page_size = cint(page_size) or DEFAULT_PAGE_SIZE
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    return page, page_size, (page - 1) * page_size


# --------------------------------------------------------------------------- #
# listings
# --------------------------------------------------------------------------- #

def listing(
    doctype,
    fields,
    filters=None,
    search=None,
    search_fields=None,
    order_by=None,
    page=1,
    page_size=DEFAULT_PAGE_SIZE,
    extra_filters=None,
):
    """A paged, searchable, permission-checked list in the shape every screen
    of the frontend expects."""
    require_user()

    filters = normalise_filters(filters)
    if extra_filters:
        filters.extend(normalise_filters(extra_filters))

    or_filters = []
    if search and search_fields:
        needle = f"%{search.strip()}%"
        or_filters = [[doctype, field, "like", needle] for field in search_fields]

    page, page_size, start = page_args(page, page_size)

    rows = frappe.get_list(
        doctype,
        fields=fields,
        filters=filters,
        or_filters=or_filters or None,
        order_by=order_by or "modified desc",
        limit_start=start,
        limit_page_length=page_size,
    )
    # count through get_all, not db.count -- only get_all applies the
    # row-level conditions, and a count that ignores them leaks how much
    # pipeline the rest of the floor is carrying.
    counted = frappe.get_list(
        doctype,
        filters=filters,
        or_filters=or_filters or None,
        fields=["count(name) as total"],
    )
    total = cint(counted[0].get("total")) if counted else 0

    return {
        "rows": serialize(rows),
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": start + len(rows) < total,
    }


def normalise_filters(filters):
    """Accept the three shapes a client might send: a dict, a list of triples,
    or nothing."""
    filters = parse(filters, default=None)
    if not filters:
        return []
    if isinstance(filters, dict):
        return [[field, "=", value] if not isinstance(value, (list, tuple)) else [field] + list(value)
                for field, value in filters.items()]
    return [list(f) for f in filters]


def date_range(filters, field, from_date=None, to_date=None):
    if from_date:
        filters.append([field, ">=", from_date])
    if to_date:
        filters.append([field, "<=", to_date])
    return filters


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #

def read_doc(doctype, name):
    """Load a document the user is actually allowed to read."""
    require_user()
    if not name or not frappe.db.exists(doctype, name):
        frappe.throw(_("{0} {1} not found").format(_(doctype), name or ""), frappe.DoesNotExistError)

    doc = frappe.get_doc(doctype, name)
    if not frappe.has_permission(doctype, "read", doc=doc):
        frappe.throw(_("Not permitted to read {0} {1}").format(_(doctype), name), frappe.PermissionError)
    return doc


def write_doc(doctype, name, data, allowed_fields):
    """Apply only the fields the API is willing to let a client set."""
    doc = read_doc(doctype, name)
    doc.check_permission("write")

    data = parse(data, default={}) or {}
    changed = []
    for field, value in data.items():
        if field not in allowed_fields:
            continue
        if doc.get(field) != value:
            doc.set(field, value)
            changed.append(field)

    if changed:
        doc.save()
    return doc, changed


def create_doc(doctype, data, allowed_fields, defaults=None):
    require_user()
    data = parse(data, default={}) or {}

    doc = frappe.new_doc(doctype)
    for field, value in (defaults or {}).items():
        doc.set(field, value)
    for field, value in data.items():
        if field in allowed_fields:
            doc.set(field, value)

    doc.insert()
    return doc


def doc_payload(doc, fields=None):
    """A document as a plain dict, child tables included."""
    payload = doc.as_dict(no_nulls=False)
    payload.pop("__islocal", None)
    payload.pop("__unsaved", None)
    if fields:
        payload = {field: payload.get(field) for field in fields}
    return serialize(payload)


def can_read(doctype):
    """Whether this login may read the doctype at all.

    Used to leave a section out of a payload instead of failing the whole
    request: sales staff often hold no permission on invoices or work orders,
    and a booking they own should still open.
    """
    if not frappe.db.exists("DocType", doctype):
        return False
    return bool(frappe.has_permission(doctype, "read"))


def user_names(users):
    """user id -> full name, for every listing that shows an owner."""
    users = [u for u in set(users or []) if u]
    if not users:
        return {}
    rows = frappe.get_list(
        "User", filters={"name": ["in", users]}, fields=["name", "full_name"], ignore_permissions=True
    )
    return {row.name: row.full_name for row in rows}


def assignments(doctype, names):
    """Open ToDo assignees per document, so a list can show who is working it."""
    names = [n for n in names or [] if n]
    if not names:
        return {}
    rows = frappe.get_list(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": ["in", names],
            "status": ["in", ["Open", "Pending"]],
        },
        fields=["reference_name", "allocated_to"],
        ignore_permissions=True,
    )
    out = {}
    for row in rows:
        out.setdefault(row.reference_name, []).append(row.allocated_to)
    return out


def assign_to(doctype, name, user, description=None):
    """Hand a record to someone. Old open assignments are closed first so a
    record has one working owner, the way the team runs it."""
    from frappe.desk.form.assign_to import add, remove

    doc = read_doc(doctype, name)
    doc.check_permission("write")

    for row in frappe.get_list(
        "ToDo",
        filters={
            "reference_type": doctype,
            "reference_name": name,
            "status": ["in", ["Open", "Pending"]],
        },
        fields=["allocated_to"],
        ignore_permissions=True,
    ):
        if row.allocated_to != user:
            remove(doctype, name, row.allocated_to)

    add(
        {
            "doctype": doctype,
            "name": name,
            "assign_to": [user],
            "description": description or _("Assigned through the CRM app"),
        }
    )
    return user
