"""Every dropdown the CRM screens need, in one call.

The frontend should never hardcode a status list: JD edits theirs, and a
mismatch between app and server shows up as a save that fails with no visible
reason. ``options()`` is one request at app start.
"""

import frappe

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_core.crm.lead_fields import (
    LEAD_SOURCES,
    LEAD_STATUSES,
    RESTRICTED_STATUSES,
    UNIT_TYPES,
)


@frappe.whitelist()
def options():
    """All select options, in one payload."""
    base.require_user()
    return ok(
        data={
            "lead": {
                "statuses": LEAD_STATUSES,
                "working_statuses": [s for s in LEAD_STATUSES if s not in RESTRICTED_STATUSES],
                "dead_statuses": RESTRICTED_STATUSES,
                "sources": LEAD_SOURCES,
                "unit_types": UNIT_TYPES,
                "facings": _select("Property Unit", "facing"),
            },
            "opportunity": {
                "statuses": _select("Opportunity", "status"),
                "types": _link_options("Opportunity Type"),
                "sources": _link_options("Lead Source"),
                "stages": _link_options("Sales Stage"),
            },
            "follow_up": {
                "types": _select("Property Follow Up", "follow_up_type"),
                "statuses": _select("Property Follow Up", "status"),
                "outcomes": _select("Property Follow Up", "outcome"),
                "reference_doctypes": _select("Property Follow Up", "reference_doctype"),
            },
            "booking": {
                "statuses": _select("Property Booking", "booking_status"),
                "payment_plan_templates": _link_options("Payment Plan Template"),
            },
            "unit": {
                "types": _select("Property Unit", "unit_type"),
                "availability": _select("Property Unit", "availability_status"),
                "facings": _select("Property Unit", "facing"),
            },
            "property": {
                "types": _select("Property", "property_type"),
                "statuses": _select("Property", "status"),
            },
            "company": _link_options("Company"),
            "currency": frappe.db.get_default("currency"),
        }
    )


@frappe.whitelist()
def field_options(doctype, fieldname):
    """One field's Select options, for a screen built after this API shipped."""
    base.require_user()
    return ok(data=_select(doctype, fieldname))


def _select(doctype, fieldname):
    if not frappe.db.exists("DocType", doctype):
        return []
    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)
    if not field or not field.options:
        return []
    return [option for option in field.options.split("\n") if option]


def _link_options(doctype, filters=None):
    if not frappe.db.exists("DocType", doctype):
        return []
    try:
        return frappe.get_list(doctype, filters=filters, pluck="name", order_by="name asc")
    except frappe.PermissionError:
        return []
