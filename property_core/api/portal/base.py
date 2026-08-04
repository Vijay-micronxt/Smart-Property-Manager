"""
Shared plumbing for the customer portal API.

Website users hold no doctype permissions, so nothing here relies on Frappe's
permission engine: every query is scoped to the customer resolved from the
session, and that resolution is the security boundary. Any endpoint taking a
unit, booking or invoice from the client must pass it through the matching
``assert_*`` guard before reading it.
"""

import datetime

import frappe

from property_core.api.portal.fields import fields_for

DATE_TYPES = (datetime.date, datetime.datetime, datetime.time, datetime.timedelta)


def get_customer():
    """Customer linked to the session user. Throws for guests and unlinked logins."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(frappe._("Please login"), frappe.AuthenticationError)

    customer = frappe.db.get_value(
        "Portal User", {"user": user, "parenttype": "Customer"}, "parent"
    )
    if not customer:
        contact = frappe.db.get_value("Contact", {"email_id": user}, "name")
        if contact:
            customer = frappe.db.get_value(
                "Dynamic Link",
                {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
                "link_name",
            )
    if not customer:
        frappe.throw(
            frappe._("No customer account is linked to your login. Please contact our team.")
        )

    return customer


def customer_units(customer):
    """Every unit the customer owns, has booked, or is allocated -- deduplicated."""
    names = set(frappe.get_all("Property Unit", filters={"customer": customer}, pluck="name"))
    names.update(
        frappe.get_all(
            "Property Booking",
            filters={"customer": customer, "docstatus": ["<", 2]},
            pluck="property_unit",
        )
    )
    names.update(
        frappe.get_all(
            "Property Allocation",
            filters={"customer": customer, "docstatus": ["<", 2]},
            pluck="property_unit",
        )
    )
    names.discard(None)
    return sorted(names)


def assert_unit(customer, property_unit):
    """Guard: the unit must be connected to this customer."""
    if property_unit not in customer_units(customer):
        frappe.throw(frappe._("Selected unit does not belong to your account"))


def assert_doc(customer, doctype, name, customer_field="customer"):
    """Guard: the document must belong to this customer."""
    if not name or not frappe.db.exists(doctype, {"name": name, customer_field: customer}):
        frappe.throw(frappe._("{0} {1} does not belong to your account").format(_(doctype), name))


def _(text):
    return frappe._(text)


def scope(customer, property_unit=None, unit_field="property_unit"):
    """Filters that keep a query inside the customer's own units.

    Returns ``None`` when the customer has no units at all, which callers treat
    as "return an empty payload" rather than running an unscoped query.
    """
    if property_unit:
        assert_unit(customer, property_unit)
        return {unit_field: property_unit}

    units = customer_units(customer)
    if not units:
        return None
    return {unit_field: ["in", units]}


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


def get_list(doctype, filters, registry_key=None, extra_fields=None, **kwargs):
    """``frappe.get_all`` with the registry's field list and date serialization."""
    fields = fields_for(doctype, registry_key=registry_key, extra=extra_fields)
    rows = frappe.get_all(doctype, filters=filters, fields=fields, **kwargs)
    return serialize(rows)


def get_one(doctype, name, registry_key=None, extra_fields=None):
    fields = fields_for(doctype, registry_key=registry_key, extra=extra_fields)
    row = frappe.db.get_value(doctype, name, fields, as_dict=True)
    return serialize(row) if row else None


def child_rows(doctype, parent, parenttype=None, parentfield=None, order_by="idx asc"):
    filters = {"parent": parent}
    if parenttype:
        filters["parenttype"] = parenttype
    if parentfield:
        filters["parentfield"] = parentfield
    return get_list(doctype, filters, order_by=order_by)


def due_status(due_date, outstanding, today=None, paid_label="Paid"):
    """Shared Paid / Overdue / Due Soon / Upcoming rule for every charge type."""
    from frappe.utils import date_diff, getdate, today as _today

    if outstanding is not None and float(outstanding or 0) <= 0:
        return paid_label
    if not due_date:
        return "Upcoming"

    today = getdate(today or _today())
    due = getdate(due_date)
    if due < today:
        return "Overdue"
    if date_diff(due, today) <= 7:
        return "Due Soon"
    return "Upcoming"


def as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
