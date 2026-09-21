"""Opportunity keeps the property side of itself straight.

Two things bit the team on the desk:

* A user picks the **unit** first -- that is how a site visit actually goes,
  "he wants plot 42" -- and then the mandatory Property field is still empty
  and the form refuses to save. The unit already knows its property, so fill
  it in instead of asking.
* Nothing stopped a unit from one development being tagged under a different
  development's property, which then feeds a booking for the wrong project.

Both are fixed here rather than only in JavaScript, because the API and the
CRM screens create opportunities too.
"""

import frappe
from frappe import _


def validate(doc, method=None):
    resolve_property_from_unit(doc)
    validate_unit_belongs_to_property(doc)
    stamp_project(doc)
    set_opportunity_owner(doc)


def resolve_property_from_unit(doc):
    """Unit chosen, property blank -- take the property off the unit."""
    if doc.get("custom_property") or not doc.get("custom_property_unit"):
        return
    doc.custom_property = frappe.db.get_value(
        "Property Unit", doc.custom_property_unit, "property"
    )


def validate_unit_belongs_to_property(doc):
    if not doc.get("custom_property_unit") or not doc.get("custom_property"):
        return

    owner_property = frappe.db.get_value("Property Unit", doc.custom_property_unit, "property")
    if owner_property and owner_property != doc.custom_property:
        frappe.throw(
            _("Unit {0} belongs to {1}, not {2}.").format(
                doc.custom_property_unit, owner_property, doc.custom_property
            )
        )


def stamp_project(doc):
    """Everything at JD is read per development, so an opportunity that cannot
    name its project is invisible in every project report."""
    if not doc.meta.has_field("custom_project"):
        return
    if doc.get("custom_property"):
        doc.custom_project = frappe.db.get_value("Property", doc.custom_property, "project")


def set_opportunity_owner(doc):
    """Ownership drives who can see the row (see crm.scope), so it must never
    be blank."""
    if not doc.get("opportunity_owner"):
        doc.opportunity_owner = doc.owner or frappe.session.user


# --------------------------------------------------------------------------- #
# used by the form and by the CRM API
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def resolve_unit(property_unit):
    """Everything the form should auto-fill once a unit is picked."""
    if not property_unit:
        return {}

    unit = frappe.db.get_value(
        "Property Unit",
        property_unit,
        [
            "name",
            "property",
            "project",
            "unit_number",
            "unit_type",
            "area",
            "facing",
            "base_price",
            "availability_status",
            "payment_plan_template",
            "customer",
        ],
        as_dict=True,
    )
    if not unit:
        return {}

    if not unit.project and unit.property:
        unit.project = frappe.db.get_value("Property", unit.property, "project")
    unit.property_name = frappe.db.get_value("Property", unit.property, "property_name")
    return unit
