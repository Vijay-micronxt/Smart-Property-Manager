"""Every dropdown the CRM screens need, in one call.

The frontend should never hardcode a status list: JD edits theirs, and a
mismatch between app and server shows up as a save that fails with no visible
reason. ``options()`` is one request at app start.
"""

import frappe

from property_core.api.crm import base
from property_core.api.utils import ok
from property_core.property_core.crm import masters


@frappe.whitelist()
def options():
    """All select options, in one payload."""
    base.require_user()
    statuses = masters.values(masters.LEAD_STATUS)
    hidden = set(masters.hidden_lead_statuses())
    rules = masters.lead_status_rules()
    return ok(
        data={
            "lead": {
                "statuses": statuses,
                "working_statuses": [s for s in statuses if s not in hidden],
                "dead_statuses": [s for s in statuses if s in hidden],
                "sources": masters.values(masters.LEAD_SOURCE),
                "unit_types": masters.values(masters.UNIT_TYPE),
                "facings": masters.values(masters.FACING),
                "status_details": [
                    {
                        "status": s,
                        "erpnext_status": rules.get(s, {}).get("erpnext_status"),
                        "hide_from_sales": bool(rules.get(s, {}).get("hide_from_sales")),
                        "indicator": rules.get(s, {}).get("indicator"),
                    }
                    for s in statuses
                ],
            },
            "opportunity": {
                "statuses": _select("Opportunity", "status"),
                "types": _link_options("Opportunity Type"),
                "sources": _link_options("Lead Source"),
                "stages": _link_options("Sales Stage"),
            },
            "follow_up": {
                "types": masters.values(masters.FOLLOW_UP_TYPE),
                "statuses": _select("Property Follow Up", "status"),
                "outcomes": masters.values(masters.FOLLOW_UP_OUTCOME),
                "reference_doctypes": _select("Property Follow Up", "reference_doctype"),
            },
            "booking": {
                "statuses": _select("Property Booking", "booking_status"),
                "payment_plan_templates": _link_options("Payment Plan Template"),
                "sales_persons": _link_options(
                    "Sales Person", filters={"is_group": 0, "enabled": 1}
                ),
            },
            "unit": {
                "types": masters.values(masters.UNIT_TYPE),
                "availability": _select("Property Unit", "availability_status"),
                "facings": masters.values(masters.FACING),
            },
            "property": {
                "types": masters.values(masters.PROPERTY_TYPE),
                "statuses": _select("Property", "status"),
            },
            "company": _link_options("Company", respect_permissions=True),
            "currency": frappe.db.get_default("currency"),
            # which master to add a new value to, for a screen that offers "+ new"
            "masters": {
                "lead.statuses": masters.LEAD_STATUS,
                "lead.sources": masters.LEAD_SOURCE,
                "follow_up.types": masters.FOLLOW_UP_TYPE,
                "follow_up.outcomes": masters.FOLLOW_UP_OUTCOME,
                "unit.types": masters.UNIT_TYPE,
                "unit.facings": masters.FACING,
                "property.types": masters.PROPERTY_TYPE,
            },
        }
    )


@frappe.whitelist()
def field_options(doctype, fieldname):
    """One field's Select options, for a screen built after this API shipped."""
    base.require_user()
    return ok(data=_select(doctype, fieldname))


def _select(doctype, fieldname):
    """A field's choices -- its Select options, or the values of the master a
    Link field points at, so a field moved from Select to Link answers the same."""
    if not frappe.db.exists("DocType", doctype):
        return []
    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)
    if not field or not field.options:
        return []
    if field.fieldtype == "Link":
        if field.options in masters.MASTERS:
            return masters.values(field.options)
        # any doctype can be asked for here, so the caller's permissions apply
        return _link_options(field.options, respect_permissions=True)
    return [option for option in field.options.split("\n") if option]


def _link_options(doctype, filters=None, respect_permissions=False):
    """Names for a dropdown. Only names go out, so a login that may not open
    the master still gets its choices -- except where the user's own
    permissions are the point (Company)."""
    if not frappe.db.exists("DocType", doctype):
        return []
    if respect_permissions:
        try:
            return frappe.get_list(doctype, filters=filters, pluck="name", order_by="name asc")
        except frappe.PermissionError:
            return []
    return frappe.get_all(doctype, filters=filters, pluck="name", order_by="name asc")
