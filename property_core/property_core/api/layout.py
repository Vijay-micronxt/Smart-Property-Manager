"""
Layout editor APIs. The editor is a desk page, so callers are logged-in desk
users -- but layout data spans Property (blueprint) and many Property Units,
so both endpoints gate on the caller's permission on the parent Property.
"""

import json

import frappe

# Fields the engine needs to draw and label a unit shape.
UNIT_FIELDS = [
    "name",
    "unit_number",
    "unit_type",
    "availability_status",
    "area",
    "base_price",
    "customer",
    "layout_shape",
    "layout_x",
    "layout_y",
    "layout_w",
    "layout_h",
    "layout_rotation",
    "layout_points",
]

STATUS_COLORS = {
    "Available": "#22c55e",
    "Reserved": "#eab308",
    "Booked": "#f97316",
    "Allocated": "#ef4444",
    "Leased": "#8b5cf6",
    "Maintenance Blocked": "#64748b",
}


def _check_property_access(property_name, ptype="read"):
    if not property_name or not frappe.db.exists("Property", property_name):
        frappe.throw(frappe._("Property {0} not found").format(property_name))
    doc = frappe.get_doc("Property", property_name)
    if not doc.has_permission(ptype):
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)
    return doc


@frappe.whitelist()
def get_layout(property):
    prop = _check_property_access(property, "read")

    units = frappe.get_all(
        "Property Unit",
        filters={"property": property},
        fields=UNIT_FIELDS,
        order_by="unit_number asc",
    )
    for unit in units:
        if unit.layout_points:
            try:
                unit.layout_points = json.loads(unit.layout_points)
            except Exception:
                unit.layout_points = None
        if unit.customer:
            unit.customer_name = frappe.db.get_value("Customer", unit.customer, "customer_name")

    annotations = []
    if prop.layout_annotations:
        try:
            annotations = json.loads(prop.layout_annotations)
        except Exception:
            annotations = []

    return {
        "property": {
            "name": prop.name,
            "property_name": prop.property_name,
            "layout_image": prop.layout_image,
            "world_width": prop.layout_world_width or 3000,
            "world_height": prop.layout_world_height or 2000,
            "annotations": annotations,
        },
        "units": units,
        "status_colors": STATUS_COLORS,
        "can_write": 1 if prop.has_permission("write") else 0,
    }


@frappe.whitelist()
def save_layout(property, units, world=None, annotations=None):
    """units: [{name, layout_shape, layout_x, layout_y, layout_w, layout_h,
    layout_rotation, layout_points}], world: {width, height, layout_image},
    annotations: [{type: "path"|"emoji", ...}] free drawing layer."""
    prop = _check_property_access(property, "write")

    if isinstance(units, str):
        units = json.loads(units)
    if isinstance(world, str):
        world = json.loads(world)
    if isinstance(annotations, str):
        annotations = json.loads(annotations)

    valid = set(
        frappe.get_all("Property Unit", filters={"property": property}, pluck="name")
    )

    for unit in units or []:
        name = unit.get("name")
        if name not in valid:
            frappe.throw(frappe._("Unit {0} does not belong to {1}").format(name, property))
        points = unit.get("layout_points")
        frappe.db.set_value(
            "Property Unit",
            name,
            {
                "layout_shape": unit.get("layout_shape") or "",
                "layout_x": frappe.utils.flt(unit.get("layout_x")),
                "layout_y": frappe.utils.flt(unit.get("layout_y")),
                "layout_w": frappe.utils.flt(unit.get("layout_w")),
                "layout_h": frappe.utils.flt(unit.get("layout_h")),
                "layout_rotation": frappe.utils.flt(unit.get("layout_rotation")),
                "layout_points": json.dumps(points) if points else "",
            },
            update_modified=False,
        )

    changed_prop = False
    if world:
        if world.get("width"):
            prop.layout_world_width = int(world["width"])
        if world.get("height"):
            prop.layout_world_height = int(world["height"])
        if "layout_image" in world:
            prop.layout_image = world["layout_image"]
        changed_prop = True

    if annotations is not None:
        prop.layout_annotations = json.dumps(annotations)
        changed_prop = True

    if changed_prop:
        prop.save()

    return {"ok": 1, "saved": len(units or [])}
