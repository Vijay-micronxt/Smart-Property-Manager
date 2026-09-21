"""Customer — the step between a won opportunity and a booking.

A booking cannot exist without one, and ERPNext's own lead conversion drops
the address on the floor, so the app's conversion (which keeps it) is what is
exposed here.
"""

import frappe
from frappe import _
from frappe.utils import flt

from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "customer_name",
    "customer_type",
    "customer_group",
    "territory",
    "mobile_no",
    "email_id",
    "lead_name",
    "default_currency",
    "disabled",
    "owner",
    "creation",
]

WRITABLE = {
    "customer_name",
    "customer_type",
    "customer_group",
    "territory",
    "mobile_no",
    "email_id",
    "tax_id",
    "default_currency",
    "lead_name",
    "id_type",
    "id_number",
    "date_of_birth",
    "nationality",
    "occupation",
    "annual_income",
    "pan_number",
    "gst_number",
}


@frappe.whitelist()
def get_customers(search=None, filters=None, page=1, page_size=20, order_by=None):
    base.require_user()
    result = base.listing(
        "Customer",
        LIST_FIELDS,
        filters=filters,
        search=search,
        search_fields=["customer_name", "mobile_no", "email_id", "name"],
        order_by=order_by or "modified desc",
        page=page,
        page_size=page_size,
    )
    return ok(data=result)


@frappe.whitelist()
def get_customer(name):
    """The customer and their whole property position."""
    doc = base.read_doc("Customer", name)
    payload = base.doc_payload(doc)

    payload["bookings"] = base.serialize(
        frappe.get_list(
            "Property Booking",
            filters={"customer": name, "docstatus": ["<", 2]},
            fields=[
                "name",
                "property_unit",
                "unit_property",
                "project",
                "booking_status",
                "total_price",
                "booking_amount",
                "booking_date",
                "docstatus",
            ],
            order_by="booking_date desc",
        )
    )
    payload["units"] = base.serialize(
        frappe.get_list(
            "Property Unit",
            filters={"customer": name},
            fields=["name", "unit_number", "property", "availability_status", "base_price"],
        )
    )
    payload["outstanding"] = _outstanding(name)
    payload["follow_ups"] = base.serialize(
        frappe.get_list(
            "Property Follow Up",
            filters={"reference_doctype": "Customer", "reference_name": name},
            fields=["name", "follow_up_type", "status", "scheduled_on", "assigned_to", "outcome"],
            order_by="scheduled_on desc",
            limit=10,
        )
    )
    return ok(data=payload)


@frappe.whitelist()
def create_customer(data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})

    if not payload.get("customer_name"):
        frappe.throw(_("Customer name is required"))

    doc = base.create_doc(
        "Customer",
        payload,
        WRITABLE,
        defaults={
            "customer_type": payload.get("customer_type") or "Individual",
            "customer_group": payload.get("customer_group")
            or frappe.db.get_single_value("Selling Settings", "customer_group")
            or "All Customer Groups",
            "territory": payload.get("territory")
            or frappe.db.get_single_value("Selling Settings", "territory")
            or "All Territories",
        },
    )
    return ok(data=base.doc_payload(doc), message=_("Customer {0} created").format(doc.name))


@frappe.whitelist()
def create_from_lead(lead):
    """Lead → Customer, address and contact carried over. Idempotent: calling
    it twice returns the customer that already exists."""
    base.read_doc("Lead", lead).check_permission("read")

    from property_core.property_core.crm.customer_from_lead import make_customer_from_lead

    customer = make_customer_from_lead(lead)
    name = customer if isinstance(customer, str) else getattr(customer, "name", customer)
    return ok(data={"customer": name}, message=_("Customer {0} ready").format(name))


def _outstanding(customer):
    if not base.can_read("Sales Invoice"):
        return {"invoices": 0, "billed": 0.0, "outstanding": 0.0, "collected": 0.0}

    rows = frappe.get_list(
        "Sales Invoice",
        filters={"customer": customer, "docstatus": 1},
        fields=[
            "count(name) as invoices",
            "sum(grand_total) as billed",
            "sum(outstanding_amount) as outstanding",
        ],
    )
    row = rows[0] if rows else {}
    return {
        "invoices": row.get("invoices") or 0,
        "billed": flt(row.get("billed"), 2),
        "outstanding": flt(row.get("outstanding"), 2),
        "collected": flt(flt(row.get("billed")) - flt(row.get("outstanding")), 2),
    }
