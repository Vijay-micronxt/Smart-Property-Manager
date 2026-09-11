"""Connections added to ERPNext-native forms, so the funnel is walkable in
both directions.

Registered through override_doctype_dashboards (see hooks.py). Each function
receives the existing dashboard dict and returns it extended -- never replaced,
or the stock connections disappear.
"""

from frappe import _

FOLLOW_UP_DYNAMIC_LINK = {"reference_name": ["reference_doctype"]}


def _extend(data, group_label, items, non_standard=None, dynamic=None):
    data = data or {}
    data.setdefault("transactions", [])
    data.setdefault("non_standard_fieldnames", {})
    data.setdefault("dynamic_links", {})

    existing = next((g for g in data["transactions"] if g.get("label") == group_label), None)
    if existing:
        existing["items"] = list(dict.fromkeys(existing.get("items", []) + items))
    else:
        data["transactions"].append({"label": group_label, "items": items})

    if non_standard:
        data["non_standard_fieldnames"].update(non_standard)
    if dynamic:
        data["dynamic_links"].update(dynamic)

    return data


def get_project_dashboard_data(data=None):
    """A Project is the construction side of a development. Everything sold out
    of it hangs off the Property, so surface both here."""
    return _extend(
        data,
        _("Property"),
        ["Property", "Property Unit", "Property Booking"],
    )


def get_lead_dashboard_data(data=None):
    return _extend(
        data,
        _("Property"),
        ["Property Follow Up", "Property Booking"],
        non_standard={"Property Follow Up": "reference_name"},
        dynamic={"reference_name": ["Lead", "reference_doctype"]},
    )


def get_opportunity_dashboard_data(data=None):
    return _extend(
        data,
        _("Property"),
        ["Property Booking", "Property Follow Up"],
        non_standard={"Property Follow Up": "reference_name"},
        dynamic={"reference_name": ["Opportunity", "reference_doctype"]},
    )


def get_customer_dashboard_data(data=None):
    return _extend(
        data,
        _("Property"),
        ["Property Booking", "Property Allocation", "Property Agreement"],
    )
