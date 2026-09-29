"""Maps and the plot layout.

* ``get_layout`` / ``save_layout`` -- the SVG site plan the desk's Plot Layout
  Editor draws: each unit's shape and position over the property's layout
  image, coloured by availability. Same data, same rules (read needs read on
  the Property, save needs write).
* ``site_map`` -- every property and unit with coordinates, for a real map
  (Google / Leaflet) with pins coloured by status.
* ``resolve_location`` / ``set_location`` -- what the desk's map search bar
  does: coordinates, a Google Maps link (short links too) or a place name ->
  a point, then saved on the property or unit.
"""

import frappe
from frappe import _
from frappe.utils import flt

from property_core.api.crm import base
from property_core.api.utils import ok

LOCATABLE = {"Property", "Property Unit"}


@frappe.whitelist()
def get_layout(property):
    base.require_user()
    from property_core.property_core.api.layout import get_layout as _get

    return ok(data=base.serialize(_get(property)))


@frappe.whitelist()
def save_layout(property, units, world=None, annotations=None):
    """``units``: ``[{name, layout_shape: Rect|Polygon|Circle, layout_x,
    layout_y, layout_w, layout_h, layout_rotation, layout_points}]``;
    ``world``: ``{width, height, layout_image}``; ``annotations``: free drawing
    layer, stored as given."""
    base.require_user()
    from property_core.property_core.api.layout import save_layout as _save

    return ok(data=_save(property, units, world, annotations), message=_("Layout saved"))


@frappe.whitelist()
def site_map(project=None, property=None, availability=None):
    """Pins: properties and their units that have coordinates."""
    base.require_user()
    from property_core.property_core.api.layout import STATUS_COLORS

    pfilters = {}
    if property:
        pfilters["name"] = property
    elif project:
        pfilters["project"] = project
    properties = frappe.get_list(
        "Property",
        filters=pfilters,
        fields=["name", "property_name", "project", "status", "latitude", "longitude", "map_link"],
    )
    ufilters = {"property": ["in", [p.name for p in properties] or [""]]}
    if availability:
        values = base.parse(availability, default=availability)
        ufilters["availability_status"] = ["in", values if isinstance(values, list) else [values]]
    units = frappe.get_list(
        "Property Unit",
        filters=ufilters,
        fields=[
            "name", "unit_number", "property", "unit_type", "availability_status",
            "area", "base_price", "latitude", "longitude",
        ],
    )
    for unit in units:
        unit["color"] = STATUS_COLORS.get(unit.availability_status)
    return ok(
        data={
            "properties": base.serialize(properties),
            "units": base.serialize([u for u in units if u.latitude and u.longitude]),
            "units_without_location": sum(1 for u in units if not (u.latitude and u.longitude)),
            "status_colors": STATUS_COLORS,
        }
    )


@frappe.whitelist()
def resolve_location(query):
    """Coordinates ("12.97, 77.59"), any Google Maps link (maps.app.goo.gl
    short links too) or a place name -> candidate points."""
    base.require_user()
    from property_core.property_core.geo import resolve

    return ok(data=resolve(query))


@frappe.whitelist()
def set_location(doctype, name, latitude=None, longitude=None, query=None):
    """Save a point on a Property or Property Unit -- either coordinates, or
    a ``query`` resolved the same way as ``resolve_location`` (first match)."""
    if doctype not in LOCATABLE:
        frappe.throw(_("Only Property and Property Unit carry a location"))
    doc = base.read_doc(doctype, name)
    doc.check_permission("write")

    if query and not (latitude and longitude):
        from property_core.property_core.geo import resolve

        results = resolve(query).get("results") or []
        if not results:
            frappe.throw(_("Could not find that place"))
        latitude, longitude = results[0]["latitude"], results[0]["longitude"]

    from property_core.property_core.geo import point_geojson

    # the map field is the source of truth; validate derives lat/lng/link from it
    doc.geo_location = point_geojson(flt(latitude), flt(longitude))
    doc.save()
    return ok(
        data={"name": name, "latitude": doc.latitude, "longitude": doc.longitude, "map_link": doc.map_link},
        message=_("Location saved"),
    )


@frappe.whitelist()
def editor_assets():
    """The layout engine the desk editor and the portal site map run on --
    a dependency-free SVG editor (draw rect / polygon / circle, drag, resize,
    rotate, vertex edit, zoom, pan, text / pencil / emoji annotations). The
    app loads these two public files from the site and gets the same editor.

    Usage: ``new PlotLayoutEngine(el, {mode: "edit", onChange, onSelect,
    onDrawComplete})``, ``engine.setData(get_layout().data)``, draw with
    ``engine.startDraw("rect"|"polygon"|"circle"|"text"|"pencil"|"eraser"|"emoji")``,
    put a drawn shape on a unit with ``engine.assignShape(unit, shape)``, and
    save ``engine.getLayoutPayload()`` + ``engine.getAnnotations()`` through
    ``save_layout``."""
    base.require_user()
    from property_core import __version__ as version
    return ok(
        data={
            "js": "/assets/property_core/js/plot_layout_engine.js",
            "css": "/assets/property_core/css/plot_layout.css",
            "version": version,
            "shapes": {
                "Rect": "layout_x, layout_y = top-left; layout_w, layout_h; layout_rotation in degrees about the centre",
                "Circle": "layout_x, layout_y = centre; layout_w = diameter",
                "Polygon": "layout_points = [[x, y], ...] (3+ points)",
            },
        }
    )


@frappe.whitelist()
def set_unit_shape(property_unit, layout_shape, layout_x=0, layout_y=0, layout_w=0, layout_h=0,
                   layout_rotation=0, layout_points=None):
    """Place (or move) one unit on its property's layout -- for a screen that
    edits a plot at a time instead of saving the whole plan."""
    prop = frappe.db.get_value("Property Unit", property_unit, "property")
    if not prop:
        frappe.throw(_("Unit {0} not found").format(property_unit), frappe.DoesNotExistError)
    if layout_shape not in ("Rect", "Polygon", "Circle", ""):
        frappe.throw(_("layout_shape must be Rect, Polygon or Circle"))
    return save_layout(
        prop,
        [{"name": property_unit, "layout_shape": layout_shape, "layout_x": layout_x, "layout_y": layout_y,
          "layout_w": layout_w, "layout_h": layout_h, "layout_rotation": layout_rotation,
          "layout_points": base.parse(layout_points, default=None)}],
    )


@frappe.whitelist()
def clear_unit_shape(property_unit):
    """Take a unit off the layout (it stays in inventory)."""
    return set_unit_shape(property_unit, "")
