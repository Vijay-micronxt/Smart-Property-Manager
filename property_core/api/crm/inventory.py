"""What there is to sell: Project → Property → Property Unit.

At JD the inventory is built before anybody sells anything — the project and
its properties exist, the units are laid out, and only then do leads arrive.
So these endpoints are read-only for sales: they pick from inventory. The two
create endpoints are for the admin setting that inventory up; the doctype's
own permissions decide who may call them (Property Manager by default).
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

PROPERTY_WRITABLE = {
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
    "map_link",
}

#: child tables an admin may replace wholesale on update_property
PROPERTY_TABLES = {"amenities", "property_documents"}

#: recurring-maintenance fields property_operations adds to Property Unit
MAINTENANCE_FIELDS = {"maintenance_plan_template", "maintenance_start_date", "pause_maintenance"}

#: statuses an admin may set by hand -- the rest (Booked, Allocated, Leased)
#: only come from a booking / allocation, or the unit and its deal disagree
MANUAL_STATUSES = {"Available", "Reserved", "Maintenance Blocked"}

UNIT_WRITABLE = {
    "property",
    "unit_number",
    "unit_type",
    "availability_status",
    "area",
    "facing",
    "floor",
    "base_price",
    "payment_plan_template",
    "latitude",
    "longitude",
    "map_link",
} | MAINTENANCE_FIELDS


@frappe.whitelist()
def create_property(data=None, **kwargs):
    """A new property. ``property_type`` is a Property Type record, so a new
    kind of property is a new record, not a code change."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in PROPERTY_WRITABLE})
    if not payload.get("company"):
        payload["company"] = frappe.defaults.get_user_default("company") or frappe.db.get_default(
            "company"
        )
    doc = base.create_doc("Property", payload, PROPERTY_WRITABLE)
    return ok(data=base.doc_payload(doc), message=frappe._("Property {0} created").format(doc.name))


@frappe.whitelist()
def create_unit(data=None, **kwargs):
    """A new unit under an existing property; project comes off the property."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in UNIT_WRITABLE})
    if not payload.get("property"):
        frappe.throw(frappe._("A unit needs a property"), frappe.MandatoryError)
    base.read_doc("Property", payload["property"])
    doc = base.create_doc(
        "Property Unit", payload, UNIT_WRITABLE, defaults={"availability_status": "Available"}
    )
    return ok(data=base.doc_payload(doc), message=frappe._("Unit {0} created").format(doc.name))


@frappe.whitelist()
def update_property(name, data=None, **kwargs):
    """Change a property. ``amenities`` / ``property_documents`` replace the
    whole table: ``[{"amenity_name": "Clubhouse", "amenity_type": "Recreation"}]``."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in PROPERTY_WRITABLE | PROPERTY_TABLES})
    tables = {k: payload.pop(k) for k in list(payload) if k in PROPERTY_TABLES}

    doc, changed = base.write_doc("Property", name, payload, PROPERTY_WRITABLE)
    if tables:
        for table, rows in tables.items():
            doc.set(table, base.parse(rows, default=[]) or [])
        doc.save()
        changed += list(tables)
    return ok(data=base.doc_payload(doc), message=frappe._("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def update_unit(name, data=None, **kwargs):
    """Change a unit. ``availability_status`` is not taken here -- use
    ``set_unit_status``; bookings and allocations move it themselves."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in UNIT_WRITABLE})
    payload.pop("availability_status", None)
    doc, changed = base.write_doc("Property Unit", name, payload, UNIT_WRITABLE)
    return ok(data=base.doc_payload(doc), message=frappe._("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def set_unit_status(name, status, reason=None):
    """Hold, release or block a unit by hand (Available / Reserved /
    Maintenance Blocked). A unit with a live booking or allocation cannot be
    moved here -- cancel that instead."""
    if status not in MANUAL_STATUSES:
        frappe.throw(
            frappe._("Status can only be set to {0} by hand").format(", ".join(sorted(MANUAL_STATUSES)))
        )
    doc = base.read_doc("Property Unit", name)
    doc.check_permission("write")
    live = frappe.db.get_value("Property Booking", {"property_unit": name, "docstatus": 1}, "name") or (
        frappe.db.get_value("Property Allocation", {"property_unit": name, "docstatus": 1}, "name")
    )
    if live and status == "Available":
        frappe.throw(frappe._("{0} is still active on this unit; cancel it first").format(live))
    doc.set_availability_status(status)
    if reason:
        doc.add_comment("Comment", text=frappe._("Status set to {0}: {1}").format(status, reason))
    return ok(data={"name": name, "availability_status": status}, message=frappe._("Unit is now {0}").format(status))


@frappe.whitelist()
def bulk_create_units(property, units=None, prefix=None, start=1, count=0, defaults=None):
    """Lay out many units in one go -- either an explicit JSON list of
    ``units`` (each like create_unit's data), or ``count`` numbered units
    ``{prefix}{start}`` … with the shared ``defaults`` (unit_type, area,
    base_price, facing, payment_plan_template …). Existing unit numbers
    under the property are skipped, so it is safe to re-run."""
    base.read_doc("Property", property)
    if not frappe.has_permission("Property Unit", "create"):
        frappe.throw(frappe._("Not permitted to create units"), frappe.PermissionError)

    shared = base.parse(defaults, default={}) or {}
    rows = base.parse(units, default=[]) or []
    if not rows and int(count or 0) > 0:
        rows = [{"unit_number": f"{prefix or ''}{n}"} for n in range(int(start or 1), int(start or 1) + int(count))]
    if not rows:
        frappe.throw(frappe._("Give units or a count"), frappe.MandatoryError)
    if len(rows) > 500:
        frappe.throw(frappe._("At most 500 units per call"))

    existing = set(frappe.get_all("Property Unit", filters={"property": property}, pluck="unit_number"))
    created, skipped = [], []
    for row in rows:
        payload = {**shared, **row, "property": property}
        if payload.get("unit_number") in existing:
            skipped.append(payload.get("unit_number"))
            continue
        doc = base.create_doc(
            "Property Unit", payload, UNIT_WRITABLE, defaults={"availability_status": "Available"}
        )
        created.append({"name": doc.name, "unit_number": doc.unit_number})
    return ok(
        data={"created": created, "skipped": skipped},
        message=frappe._("{0} unit(s) created, {1} skipped").format(len(created), len(skipped)),
    )


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
