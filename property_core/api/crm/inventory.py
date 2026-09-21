"""What there is to sell: Project → Property → Property Unit.

At JD the inventory is built before anybody sells anything — the project and
its properties exist, the units are laid out, and only then do leads arrive.
So these endpoints are read-only for sales: they pick from inventory, they do
not create it.
"""

import frappe
from frappe.utils import flt

from property_core.api.crm import base
from property_core.api.utils import ok

PROPERTY_FIELDS = [
    "name",
    "property_name",
    "property_type",
    "status",
    "project",
    "company",
    "launch_date",
    "total_area",
    "address",
    "payment_plan_template",
    "latitude",
    "longitude",
    "layout_image",
]

UNIT_FIELDS = [
    "name",
    "unit_number",
    "property",
    "project",
    "unit_type",
    "availability_status",
    "area",
    "facing",
    "floor",
    "base_price",
    "payment_plan_template",
    "customer",
    "item_code",
    "latitude",
    "longitude",
]

SELLABLE = ["Available", "Reserved"]


@frappe.whitelist()
def get_properties(
    project=None, search=None, status=None, property_type=None, page=1, page_size=20, order_by=None
):
    base.require_user()

    conditions = []
    if project:
        conditions.append(["project", "=", project])
    if status:
        conditions.append(["status", "=", status])
    if property_type:
        conditions.append(["property_type", "=", property_type])

    result = base.listing(
        "Property",
        PROPERTY_FIELDS,
        extra_filters=conditions,
        search=search,
        search_fields=["property_name", "name", "address"],
        order_by=order_by or "property_name asc",
        page=page,
        page_size=page_size,
    )

    stats = unit_stats([row["name"] for row in result["rows"]])
    for row in result["rows"]:
        row["units"] = stats.get(row["name"], _empty_stats())
    return ok(data=result)


@frappe.whitelist()
def get_property(name):
    doc = base.read_doc("Property", name)
    payload = base.doc_payload(doc)
    payload["units"] = unit_stats([name]).get(name, _empty_stats())
    payload["project_name"] = frappe.db.get_value("Project", doc.get("project"), "project_name")
    return ok(data=payload)


@frappe.whitelist()
def get_units(
    property=None,
    project=None,
    availability=None,
    unit_type=None,
    facing=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    search=None,
    page=1,
    page_size=20,
    order_by=None,
):
    """The unit picker behind every property/unit dropdown in the app."""
    base.require_user()

    conditions = []
    if property:
        conditions.append(["property", "=", property])
    if project:
        conditions.append(["property", "in", _properties_of(project)])
    if availability:
        values = base.parse(availability, default=availability)
        conditions.append(
            ["availability_status", "in", values if isinstance(values, list) else [values]]
        )
    if unit_type:
        conditions.append(["unit_type", "=", unit_type])
    if facing:
        conditions.append(["facing", "=", facing])
    if min_price:
        conditions.append(["base_price", ">=", flt(min_price)])
    if max_price:
        conditions.append(["base_price", "<=", flt(max_price)])
    if min_area:
        conditions.append(["area", ">=", flt(min_area)])
    if max_area:
        conditions.append(["area", "<=", flt(max_area)])

    result = base.listing(
        "Property Unit",
        UNIT_FIELDS,
        extra_filters=conditions,
        search=search,
        search_fields=["unit_number", "name"],
        order_by=order_by or "property asc, unit_number asc",
        page=page,
        page_size=page_size,
    )
    return ok(data=result)


@frappe.whitelist()
def available_units(
    property=None,
    project=None,
    search=None,
    unit_type=None,
    facing=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    page=1,
    page_size=50,
    order_by=None,
):
    """Only what can still be sold — what the opportunity screen offers."""
    return get_units(
        property=property,
        project=project,
        availability=SELLABLE,
        unit_type=unit_type,
        facing=facing,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        search=search,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )


@frappe.whitelist()
def get_unit(name):
    doc = base.read_doc("Property Unit", name)
    payload = base.doc_payload(doc)
    payload["property_name"] = frappe.db.get_value("Property", doc.get("property"), "property_name")
    payload["open_booking"] = frappe.db.get_value(
        "Property Booking", {"property_unit": name, "docstatus": ["<", 2]}, "name"
    )
    payload["opportunities"] = base.serialize(
        frappe.get_list(
            "Opportunity",
            filters={"custom_property_unit": name, "status": ["not in", ["Lost", "Closed"]]},
            fields=["name", "party_name", "status", "opportunity_amount", "opportunity_owner"],
            limit=20,
        )
    )
    return ok(data=payload)


@frappe.whitelist()
def resolve_unit(property_unit):
    """Given a unit, everything a form should fill in around it — property,
    project, price, plan. This is the call that stops a user having to name the
    development they just picked a plot out of.
    """
    base.require_user()
    from property_core.property_core.crm.opportunity_events import resolve_unit as _resolve

    return ok(data=base.serialize(_resolve(property_unit)))


@frappe.whitelist()
def availability(project=None, property=None):
    """Inventory position — the number every review meeting starts with."""
    base.require_user()

    filters = {}
    if property:
        filters["property"] = property
    elif project:
        filters["property"] = ["in", _properties_of(project)]

    rows = frappe.get_list(
        "Property Unit",
        filters=filters,
        fields=[
            "availability_status as status",
            "count(name) as total",
            "sum(base_price) as value",
            "sum(area) as area",
        ],
        group_by="availability_status",
    )
    total = sum(row.total for row in rows)
    return ok(
        data={
            "total_units": total,
            "by_status": rows,
            "available": next((r.total for r in rows if r.status == "Available"), 0),
            "booked": sum(r.total for r in rows if r.status in ("Booked", "Allocated")),
            "value": flt(sum(flt(r.value) for r in rows), 2),
        }
    )


def unit_stats(properties):
    """Per-property unit counts, in one query rather than one per card."""
    properties = [p for p in properties or [] if p]
    if not properties:
        return {}

    rows = frappe.get_list(
        "Property Unit",
        filters={"property": ["in", properties]},
        fields=[
            "property",
            "availability_status",
            "count(name) as total",
            "sum(base_price) as value",
        ],
        group_by="property, availability_status",
    )

    out = {}
    for row in rows:
        entry = out.setdefault(row.property, _empty_stats())
        entry["total"] += row.total
        entry["value"] = flt(entry["value"] + flt(row.value), 2)
        key = (row.availability_status or "").lower().replace(" ", "_")
        entry[key] = entry.get(key, 0) + row.total
    return out


def _empty_stats():
    return {"total": 0, "available": 0, "reserved": 0, "booked": 0, "allocated": 0, "value": 0.0}


def _properties_of(project):
    return frappe.get_list("Property", filters={"project": project}, pluck="name") or [""]
