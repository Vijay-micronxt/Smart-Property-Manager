"""Units, properties/projects and the site map the customer can see."""

import json

import frappe

from property_core.api.portal.base import (
    as_int,
    assert_unit,
    child_rows,
    customer_units,
    get_customer,
    get_list,
    get_one,
    serialize,
)
from property_core.api.utils import ok
from property_core.property_core.api.layout import STATUS_COLORS


@frappe.whitelist()
def my_units():
    """Every unit the customer owns, booked or is allocated, with its property/project."""
    customer = get_customer()
    units = customer_units(customer)
    if not units:
        return ok(data={"units": [], "total": 0})

    rows = get_list("Property Unit", {"name": ["in", units]}, order_by="property asc, unit_number asc")
    for row in rows:
        row["property_name"] = frappe.db.get_value("Property", row.get("property"), "property_name")
        if row.get("project"):
            row["project_name"] = frappe.db.get_value("Project", row["project"], "project_name")
        row["is_owner"] = 1 if row.get("customer") == customer else 0
        row.pop("customer", None)

    return ok(data={"units": rows, "total": len(rows)})


@frappe.whitelist()
def unit(property_unit):
    """Full detail for one unit: property, project, allocation, agreement, amenities."""
    customer = get_customer()
    assert_unit(customer, property_unit)

    row = get_one("Property Unit", property_unit)
    if not row:
        frappe.throw(frappe._("Unit not found"))
    row["is_owner"] = 1 if row.get("customer") == customer else 0
    row.pop("customer", None)

    property_row = get_one("Property", row.get("property")) if row.get("property") else None
    amenities = (
        child_rows("Property Amenity", row["property"], parenttype="Property")
        if row.get("property") else []
    )
    documents = (
        child_rows("Property Document", row["property"], parenttype="Property")
        if row.get("property") else []
    )

    allocation = get_list(
        "Property Allocation",
        {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
        order_by="creation desc", limit_page_length=1,
    )
    agreement = get_list(
        "Property Agreement",
        {"property_unit": property_unit, "customer": customer},
        order_by="creation desc", limit_page_length=1,
    )
    booking = get_list(
        "Property Booking",
        {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
        order_by="creation desc", limit_page_length=1,
    )

    project = None
    if row.get("project"):
        project = frappe.db.get_value(
            "Project", row["project"],
            ["name", "project_name", "status", "percent_complete", "expected_start_date",
             "expected_end_date"],
            as_dict=True,
        )

    return ok(data=serialize({
        "unit": row,
        "property": property_row,
        "project": project,
        "amenities": amenities,
        "property_documents": documents,
        "allocation": allocation[0] if allocation else None,
        "agreement": agreement[0] if agreement else None,
        "booking": booking[0] if booking else None,
    }))


@frappe.whitelist()
def projects():
    """Properties (and their ERPNext Projects) the customer is involved in."""
    customer = get_customer()
    units = customer_units(customer)
    if not units:
        return ok(data={"properties": [], "total": 0})

    property_names = sorted({
        p for p in frappe.get_all(
            "Property Unit", filters={"name": ["in", units]}, pluck="property"
        ) if p
    })

    rows = get_list("Property", {"name": ["in", property_names]}, order_by="property_name asc") if property_names else []
    for row in rows:
        row["my_unit_count"] = frappe.db.count(
            "Property Unit", {"name": ["in", units], "property": row["name"]}
        )
        if row.get("project"):
            row["project_details"] = serialize(frappe.db.get_value(
                "Project", row["project"],
                ["name", "project_name", "status", "percent_complete",
                 "expected_start_date", "expected_end_date"],
                as_dict=True,
            ))

    return ok(data={"properties": rows, "total": len(rows)})


@frappe.whitelist()
def site_map(property=None):
    """Layout geometry for the map view.

    Covers every Active property that has a blueprint, plus any property the
    customer holds a unit in. Other customers' identities are never exposed --
    only the unit's status and whether it is the caller's own.
    """
    customer = get_customer()

    names = set()
    if property:
        names.add(property)
    else:
        units = customer_units(customer)
        if units:
            names.update(
                p for p in frappe.get_all(
                    "Property Unit", filters={"name": ["in", units]}, pluck="property"
                ) if p
            )
        names.update(
            frappe.get_all(
                "Property",
                filters={"status": "Active", "layout_image": ["!=", ""]},
                pluck="name",
            )
        )
    names.discard(None)

    my_units = set(customer_units(customer))
    properties = []
    for name in sorted(names):
        prop = frappe.db.get_value(
            "Property", name,
            ["name", "property_name", "project", "layout_image", "layout_world_width",
             "layout_world_height", "layout_annotations"],
            as_dict=True,
        )
        if not prop:
            continue

        annotations = []
        if prop.layout_annotations:
            try:
                annotations = json.loads(prop.layout_annotations)
            except ValueError:
                annotations = []

        units = get_list(
            "Property Unit", {"property": name},
            registry_key="Property Unit Layout", order_by="unit_number asc",
        )
        for row in units:
            if row.get("layout_points"):
                try:
                    row["layout_points"] = json.loads(row["layout_points"])
                except ValueError:
                    row["layout_points"] = None
            row["mine"] = 1 if row["name"] in my_units else 0
            row["bookable"] = 1 if row.get("availability_status") == "Available" else 0
            row.pop("customer", None)

        properties.append({
            "property": {
                "name": prop.name,
                "property_name": prop.property_name,
                "project": prop.project,
                "layout_image": prop.layout_image,
                "world_width": prop.layout_world_width or 3000,
                "world_height": prop.layout_world_height or 2000,
                "annotations": annotations,
            },
            "units": units,
        })

    return ok(data={"properties": properties, "status_colors": STATUS_COLORS})


@frappe.whitelist()
def available_units(property=None, unit_type=None, limit=200):
    """Bookable inventory -- what the customer can actually book from the portal."""
    get_customer()

    filters = {"availability_status": "Available"}
    if property:
        filters["property"] = property
    if unit_type:
        filters["unit_type"] = unit_type

    rows = get_list(
        "Property Unit", filters,
        order_by="property asc, unit_number asc",
        limit_page_length=as_int(limit, 200),
    )
    for row in rows:
        row.pop("customer", None)
        row["property_name"] = frappe.db.get_value("Property", row.get("property"), "property_name")

    return ok(data={"units": rows, "total": len(rows)})
