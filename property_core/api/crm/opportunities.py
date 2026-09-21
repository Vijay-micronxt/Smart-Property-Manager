"""Opportunity — requirement agreed, property tagged, ready to book.

This is the hinge of the funnel: a lead becomes an opportunity when there is a
real requirement, and an opportunity becomes a Property Booking when the unit
is taken. Both the property and the unit live on the opportunity, so the
booking can be raised without anyone re-keying what was already agreed.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "opportunity_from",
    "party_name",
    "customer_name",
    "contact_person",
    "contact_email",
    "contact_mobile",
    "status",
    "sales_stage",
    "opportunity_amount",
    "probability",
    "expected_closing",
    "contact_date",
    "transaction_date",
    "custom_property",
    "custom_property_unit",
    "custom_project",
    "opportunity_owner",
    "source",
    "company",
    "owner",
    "creation",
    "modified",
]

WRITABLE = {
    "opportunity_from",
    "party_name",
    "status",
    "sales_stage",
    "opportunity_amount",
    "probability",
    "expected_closing",
    "contact_date",
    "source",
    "opportunity_type",
    "custom_property",
    "custom_property_unit",
    "opportunity_owner",
    "contact_person",
    "contact_email",
    "contact_mobile",
    "territory",
    "company",
    "currency",
}


@frappe.whitelist()
def get_opportunities(
    search=None,
    status=None,
    property=None,
    project=None,
    property_unit=None,
    owner=None,
    mine=None,
    from_date=None,
    to_date=None,
    filters=None,
    order_by=None,
    page=1,
    page_size=20,
):
    user = base.require_user()

    conditions = []
    if status:
        statuses = base.parse(status, default=status)
        conditions.append(["status", "in", statuses if isinstance(statuses, list) else [statuses]])
    if property:
        conditions.append(["custom_property", "=", property])
    if project:
        conditions.append(["custom_project", "=", project])
    if property_unit:
        conditions.append(["custom_property_unit", "=", property_unit])
    if owner:
        conditions.append(["opportunity_owner", "=", owner])
    if base.as_bool(mine):
        conditions.append(["opportunity_owner", "=", user])
    base.date_range(conditions, "transaction_date", from_date, to_date)

    result = base.listing(
        "Opportunity",
        LIST_FIELDS,
        filters=filters,
        extra_filters=conditions,
        search=search,
        search_fields=["party_name", "customer_name", "contact_mobile", "contact_email", "name"],
        order_by=order_by or "modified desc",
        page=page,
        page_size=page_size,
    )

    owners = base.user_names([row.get("opportunity_owner") for row in result["rows"]])
    for row in result["rows"]:
        row["opportunity_owner_name"] = owners.get(row.get("opportunity_owner"))
    return ok(data=result)


@frappe.whitelist()
def get_opportunity(name):
    doc = base.read_doc("Opportunity", name)
    payload = base.doc_payload(doc)

    payload["unit"] = _unit_summary(doc.get("custom_property_unit"))
    payload["property_name"] = frappe.db.get_value(
        "Property", doc.get("custom_property"), "property_name"
    )
    payload["follow_ups"] = base.serialize(
        frappe.get_list(
            "Property Follow Up",
            filters={"reference_doctype": "Opportunity", "reference_name": name},
            fields=["name", "follow_up_type", "status", "scheduled_on", "assigned_to", "outcome", "notes"],
            order_by="scheduled_on desc",
            limit=20,
        )
    )
    payload["bookings"] = base.serialize(
        frappe.get_list(
            "Property Booking",
            filters={"opportunity": name},
            fields=["name", "booking_status", "property_unit", "total_price", "booking_date", "docstatus"],
            order_by="creation desc",
        )
    )
    payload["customer"] = _customer_for(doc)
    payload["can_book"] = bool(doc.get("custom_property_unit")) and doc.status not in ("Lost", "Closed")
    return ok(data=payload)


@frappe.whitelist()
def create_opportunity(data=None, **kwargs):
    """A direct opportunity — a walk-in who never was a lead, or one raised
    against an existing customer."""
    user = base.require_user()
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})

    if payload.get("property_unit") and not payload.get("custom_property_unit"):
        payload["custom_property_unit"] = payload.pop("property_unit")

    if not payload.get("custom_property") and payload.get("custom_property_unit"):
        payload["custom_property"] = frappe.db.get_value(
            "Property Unit", payload["custom_property_unit"], "property"
        )
    if not payload.get("custom_property"):
        frappe.throw(_("Pick a property — an opportunity cannot be worked without one."))

    if not payload.get("opportunity_amount") and payload.get("custom_property_unit"):
        payload["opportunity_amount"] = frappe.db.get_value(
            "Property Unit", payload["custom_property_unit"], "base_price"
        )

    doc = base.create_doc(
        "Opportunity",
        payload,
        WRITABLE,
        defaults={
            "opportunity_from": payload.get("opportunity_from") or "Lead",
            "opportunity_owner": payload.get("opportunity_owner") or user,
            "transaction_date": payload.get("transaction_date") or today(),
        },
    )
    return ok(data=base.doc_payload(doc), message=_("Opportunity {0} created").format(doc.name))


@frappe.whitelist()
def update_opportunity(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    doc, changed = base.write_doc("Opportunity", name, payload, WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def set_property(name, property=None, property_unit=None):
    """Tag the development and the unit.

    Sending only a unit is normal and enough — the property comes off the unit,
    the same way the desk form fills it in. Sending a unit that belongs to
    another property is refused rather than silently retagged.
    """
    doc = base.read_doc("Opportunity", name)
    doc.check_permission("write")

    if property_unit:
        unit_property = frappe.db.get_value("Property Unit", property_unit, "property")
        if property and unit_property and property != unit_property:
            frappe.throw(
                _("Unit {0} belongs to {1}, not {2}.").format(property_unit, unit_property, property)
            )
        property = property or unit_property

    if property:
        doc.custom_property = property
    doc.custom_property_unit = property_unit or None

    if doc.custom_property_unit and not doc.opportunity_amount:
        doc.opportunity_amount = frappe.db.get_value(
            "Property Unit", doc.custom_property_unit, "base_price"
        )

    doc.save()
    return ok(
        data={
            "name": doc.name,
            "custom_property": doc.custom_property,
            "custom_property_unit": doc.custom_property_unit,
            "custom_project": doc.get("custom_project"),
            "opportunity_amount": doc.opportunity_amount,
            "unit": _unit_summary(doc.custom_property_unit),
        },
        message=_("Property updated"),
    )


@frappe.whitelist()
def set_status(name, status, reason=None):
    doc = base.read_doc("Opportunity", name)
    doc.check_permission("write")

    doc.status = status
    if status == "Lost" and reason:
        doc.order_lost_reason = reason
    doc.save()
    return ok(data={"name": name, "status": doc.status})


@frappe.whitelist()
def convert_to_booking(
    name,
    booking_date=None,
    booking_amount=0,
    total_price=None,
    payment_plan_template=None,
    sales_person=None,
    property_unit=None,
    notes=None,
    submit=0,
):
    """Opportunity → Property Booking.

    Everything that can be derived is derived: the unit and property come off
    the opportunity, the agreement value off the unit's base price, and the
    customer off the lead (created if the lead was never converted, because a
    booking cannot exist without one).
    """
    doc = base.read_doc("Opportunity", name)
    doc.check_permission("read")

    unit = property_unit or doc.get("custom_property_unit")
    if not unit:
        frappe.throw(_("Tag the unit on the opportunity before booking it."))

    existing = frappe.db.get_value(
        "Property Booking", {"opportunity": name, "docstatus": ["<", 2]}, "name"
    )
    if existing:
        return ok(
            data={"name": existing, "already_existed": True},
            message=_("Booking {0} already exists for this opportunity").format(existing),
        )

    customer = _customer_for(doc)
    if not customer:
        customer = _create_customer(doc)

    from property_core.property_core.doctype.property_booking.property_booking import (
        make_from_opportunity,
    )

    booking = make_from_opportunity(name)
    booking.property_unit = unit
    booking.unit_property = frappe.db.get_value("Property Unit", unit, "property")
    booking.customer = customer
    booking.booking_date = booking_date or today()
    booking.booking_amount = flt(booking_amount)
    if total_price:
        booking.total_price = flt(total_price)
    if payment_plan_template:
        booking.payment_plan_template = payment_plan_template
    if sales_person:
        booking.sales_person = sales_person
    if notes:
        booking.notes = notes

    booking.insert()
    if base.as_bool(submit):
        booking.submit()

    return ok(
        data=base.doc_payload(booking),
        message=_("Booking {0} created").format(booking.name),
    )


@frappe.whitelist()
def funnel(from_date=None, to_date=None, project=None):
    """Opportunity counts and value per status, scoped to the caller."""
    base.require_user()

    filters = []
    base.date_range(filters, "transaction_date", from_date, to_date)
    if project:
        filters.append(["custom_project", "=", project])

    rows = frappe.get_list(
        "Opportunity",
        filters=filters,
        fields=["status", "count(name) as total", "sum(opportunity_amount) as value"],
        group_by="status",
        order_by="total desc",
    )
    return ok(
        data={
            "total": sum(row.total for row in rows),
            "value": flt(sum(flt(row.value) for row in rows), 2),
            "by_status": rows,
        }
    )


# --------------------------------------------------------------------------- #

def _customer_for(doc):
    if doc.opportunity_from == "Customer":
        return doc.party_name
    if doc.get("customer"):
        return doc.customer
    if doc.opportunity_from == "Lead":
        return frappe.db.get_value("Customer", {"lead_name": doc.party_name}, "name")
    return None


def _create_customer(doc):
    if doc.opportunity_from != "Lead" or not doc.party_name:
        frappe.throw(_("This opportunity has no customer and none can be derived from it."))

    from property_core.property_core.crm.customer_from_lead import make_customer_from_lead

    customer = make_customer_from_lead(doc.party_name)
    return customer if isinstance(customer, str) else getattr(customer, "name", customer)


def _unit_summary(property_unit):
    if not property_unit:
        return None
    from property_core.property_core.crm.opportunity_events import resolve_unit

    return base.serialize(resolve_unit(property_unit))
