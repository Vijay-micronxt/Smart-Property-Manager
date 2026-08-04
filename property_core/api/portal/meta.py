"""Portal bootstrap: everything the frontend needs before it renders a screen."""

import frappe

from property_core.api.portal.base import get_customer
from property_core.api.utils import ok
from property_core.property_core.api.layout import STATUS_COLORS

# Bumped whenever a payload shape changes in a way a client must notice.
API_VERSION = "1.0.0"


@frappe.whitelist()
def settings():
    """Labels, colours, currency and feature flags -- so the client hardcodes none of it."""
    customer = get_customer()

    company = (
        frappe.db.get_single_value("Property Core Settings", "default_company")
        or frappe.defaults.get_user_default("Company")
    )
    currency = (
        frappe.db.get_value("Company", company, "default_currency") if company else None
    ) or frappe.db.get_default("currency") or "INR"

    return ok(data={
        "api_version": API_VERSION,
        "customer": customer,
        "currency": currency,
        "company": company,
        "status_colors": STATUS_COLORS,
        "unit_statuses": _select_options("Property Unit", "availability_status"),
        "unit_types": _select_options("Property Unit", "unit_type"),
        "booking_statuses": _select_options("Property Booking", "booking_status"),
        "issue_statuses": _select_options("Issue", "status"),
        "issue_priorities": frappe.get_all("Issue Priority", pluck="name"),
        "charge_types": ["Booking Milestone", "Maintenance", "Utility", "Rent", "Other"],
        "charge_statuses": ["Paid", "Overdue", "Due Soon", "Upcoming"],
        "features": {
            "booking": True,
            "issues": True,
            "maintenance": frappe.db.exists("DocType", "Work Order") and True or False,
            "utilities": frappe.db.exists("DocType", "Utility Bill") and True or False,
            "inspections": frappe.db.exists("DocType", "Inspection Checklist") and True or False,
            "site_map": True,
        },
    })


def _select_options(doctype, fieldname):
    meta = frappe.get_meta(doctype)
    df = meta.get_field(fieldname)
    if not df or not df.options:
        return []
    return [opt for opt in df.options.split("\n") if opt]
