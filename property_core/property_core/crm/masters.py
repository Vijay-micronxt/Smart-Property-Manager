"""Dropdown masters: the values JD edits themselves, kept in DocTypes.

Lead status, lead source, follow-up type and outcome, unit type, facing and
property type used to be Select fields whose options lived in this app's code.
Adding a value meant a code change and a deploy, and ``bench migrate`` wiped
anything added from the desk. They are now Link fields onto small masters, so
a new value is a new record.

Only labels moved. Fields the code branches on (unit availability, booking
status, follow-up status, property status) stay Select on purpose.

``setup_masters`` runs on every migrate and is safe to re-run:

1. first run only, per master: seed it from the old option lists, any options
   the site had added through Customize Form, and every value already stored
   on a record -- so no existing document ends up pointing at a missing link;
2. flip the app's Lead/Opportunity Custom Fields from Select to Link (Frappe
   refuses that change through the Custom Field form; the column is varchar
   either way, so no data moves);
3. drop Property Setters that would still force the old Select options.
"""

import frappe

from property_core.property_core.crm.lead_fields import (
    LEAD_SOURCES,
    LEAD_STATUSES,
    RESTRICTED_STATUSES,
    STATUS_MAP,
    UNIT_TYPES,
)

CACHE_KEY = "property_core:dropdown_masters"

LEAD_STATUS = "Property Lead Status"
LEAD_SOURCE = "Lead Source"  # ERPNext's own master, reused
FOLLOW_UP_TYPE = "Property Follow Up Type"
FOLLOW_UP_OUTCOME = "Property Follow Up Outcome"
UNIT_TYPE = "Property Unit Type"
FACING = "Property Facing"
PROPERTY_TYPE = "Property Type"

WON_STATUSES = ["Booked", "converted"]
RED_STATUSES = [
    "Junk",
    "Duplicate",
    "DND",
    "Not Interested",
    "Number Invalid",
    "Already Purchased",
    "Dropped the Plan",
]

#: master -> (name field, seed values, fields that link to it)
MASTERS = {
    LEAD_STATUS: (
        "status_name",
        LEAD_STATUSES,
        [("Lead", "custom_lead_status")],
    ),
    LEAD_SOURCE: (
        "source_name",
        LEAD_SOURCES,
        [("Lead", "custom_lead_source")],
    ),
    FOLLOW_UP_TYPE: (
        "type_name",
        ["Call", "WhatsApp", "Email", "Site Visit", "Meeting", "Other"],
        [("Property Follow Up", "follow_up_type")],
    ),
    FOLLOW_UP_OUTCOME: (
        "outcome_name",
        [
            "Connected",
            "Not Connected",
            "Callback Requested",
            "Interested",
            "Not Interested",
            "Site Visit Booked",
            "Site Visit Done",
            "Negotiating",
            "Converted",
            "Lost",
        ],
        [("Property Follow Up", "outcome")],
    ),
    UNIT_TYPE: (
        "unit_type",
        UNIT_TYPES,
        [
            ("Property Unit", "unit_type"),
            ("Lead", "custom_unit_type"),
            ("Opportunity", "custom_unit_type"),
        ],
    ),
    FACING: (
        "facing",
        ["North", "South", "East", "West", "North-East", "North-West", "South-East", "South-West"],
        [
            ("Property Unit", "facing"),
            ("Lead", "custom_preferred_facing"),
            ("Opportunity", "custom_preferred_facing"),
        ],
    ),
    PROPERTY_TYPE: (
        "property_type",
        ["Township", "Community", "Apartment", "Farmland", "Commercial Complex", "Industrial"],
        [("Property", "property_type")],
    ),
}

#: Lead/Opportunity fields this app creates as Custom Fields
CUSTOM_FIELD_TARGETS = {
    ("Lead", "custom_lead_status"): LEAD_STATUS,
    ("Lead", "custom_lead_source"): LEAD_SOURCE,
    ("Lead", "custom_unit_type"): UNIT_TYPE,
    ("Lead", "custom_preferred_facing"): FACING,
    ("Opportunity", "custom_unit_type"): UNIT_TYPE,
    ("Opportunity", "custom_preferred_facing"): FACING,
}


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #


def clear_master_cache(*args, **kwargs):
    frappe.cache().delete_value(CACHE_KEY)


def _load():
    data = {}
    for doctype in MASTERS:
        if not frappe.db.table_exists(doctype):
            data[doctype] = []
            continue
        if doctype == LEAD_SOURCE:
            # no enabled flag or ordering on ERPNext's master
            data[doctype] = frappe.get_all(doctype, pluck="name", order_by="name asc")
            continue
        data[doctype] = frappe.get_all(
            doctype,
            filters={"enabled": 1},
            pluck="name",
            order_by="sort_order asc, name asc",
        )

    data["_lead_status_rules"] = {}
    if frappe.db.table_exists(LEAD_STATUS):
        for row in frappe.get_all(
            LEAD_STATUS,
            fields=["name", "erpnext_status", "hide_from_sales", "indicator", "enabled"],
            order_by="sort_order asc, name asc",
        ):
            data["_lead_status_rules"][row.name] = {
                "erpnext_status": row.erpnext_status or "Open",
                "hide_from_sales": row.hide_from_sales,
                "indicator": row.indicator or "blue",
                "enabled": row.enabled,
            }
    return data


def _cached():
    data = frappe.cache().get_value(CACHE_KEY)
    if data is None:
        data = _load()
        frappe.cache().set_value(CACHE_KEY, data)
    return data


def values(doctype):
    """Enabled values of one master, in dropdown order."""
    return list(_cached().get(doctype) or [])


def lead_status_rules():
    """status -> {erpnext_status, hide_from_sales, indicator, enabled}."""
    rules = _cached().get("_lead_status_rules")
    if rules:
        return rules
    # master not there yet (mid-migrate): the old hardcoded behaviour
    return {
        status: {
            "erpnext_status": STATUS_MAP.get(status, "Open"),
            "hide_from_sales": int(status in RESTRICTED_STATUSES),
            "indicator": _default_indicator(status),
            "enabled": 1,
        }
        for status in LEAD_STATUSES
    }


def hidden_lead_statuses():
    """Statuses dropped from sales users' lead lists."""
    return [name for name, rule in lead_status_rules().items() if rule["hide_from_sales"]]


def erpnext_status_for(status):
    rule = lead_status_rules().get(status)
    return (rule or {}).get("erpnext_status") or STATUS_MAP.get(status, "Open")


def _default_indicator(status):
    if status in WON_STATUSES:
        return "green"
    if status in RED_STATUSES:
        return "red"
    if status == "New":
        return "blue"
    return "orange"


@frappe.whitelist()
def lead_status_indicators():
    """For the Lead list view: status -> indicator colour."""
    return {name: rule["indicator"] for name, rule in lead_status_rules().items()}


# --------------------------------------------------------------------------- #
# migrate
# --------------------------------------------------------------------------- #


def setup_masters():
    """after_migrate hook. Must run before ``sync_lead_crm_fields``."""
    for doctype, (name_field, defaults, targets) in MASTERS.items():
        if not frappe.db.table_exists(doctype):
            continue
        flag = f"property_core_seeded:{doctype}"
        if not frappe.db.get_default(flag):
            _seed(doctype, name_field, defaults, targets)
            frappe.db.set_default(flag, "1")

    _convert_custom_fields()
    _drop_select_property_setters()

    for doctype in {dt for _m, (_f, _d, targets) in MASTERS.items() for dt, _fn in targets}:
        frappe.clear_cache(doctype=doctype)
    clear_master_cache()
    frappe.db.commit()


def _seed(doctype, name_field, defaults, targets):
    wanted = []
    for value in defaults:
        _add(wanted, value)
    for dt, fieldname in targets:
        for value in _property_setter_options(dt, fieldname):
            _add(wanted, value)
        for value in _stored_values(dt, fieldname):
            _add(wanted, value)

    existing = {name.lower() for name in frappe.get_all(doctype, pluck="name")}
    for position, value in enumerate(wanted, start=1):
        if value.lower() in existing:
            continue
        row = {"doctype": doctype, name_field: value}
        if doctype != LEAD_SOURCE:
            row["sort_order"] = position
            row["enabled"] = 1
        if doctype == LEAD_STATUS:
            row.update(
                {
                    "erpnext_status": STATUS_MAP.get(value, "Open"),
                    "hide_from_sales": int(value in RESTRICTED_STATUSES),
                    "indicator": _default_indicator(value),
                }
            )
        try:
            frappe.get_doc(row).insert(ignore_permissions=True)
            existing.add(value.lower())
        except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
            existing.add(value.lower())


def _add(bucket, value):
    value = (value or "").strip()
    if value and value.lower() not in {v.lower() for v in bucket}:
        bucket.append(value)


def _property_setter_options(doctype, fieldname):
    """Options a site added through Customize Form, while the field was a Select."""
    raw = frappe.db.get_value(
        "Property Setter",
        {"doc_type": doctype, "field_name": fieldname, "property": "options"},
        "value",
    )
    if not raw or "\n" not in raw and frappe.db.exists("DocType", raw):
        return []
    return [line for line in raw.split("\n") if line.strip()]


def _stored_values(doctype, fieldname):
    """Every value already sitting on a record, so none of them breaks as a link."""
    if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, fieldname):
        return []
    return [
        row[0]
        for row in frappe.db.sql(
            f"select distinct `{fieldname}` from `tab{doctype}` where ifnull(`{fieldname}`, '') != ''"
        )
    ]


def _convert_custom_fields():
    for (doctype, fieldname), master in CUSTOM_FIELD_TARGETS.items():
        name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
        if not name:
            continue
        if frappe.db.get_value("Custom Field", name, "fieldtype") == "Select":
            frappe.db.set_value(
                "Custom Field",
                name,
                {"fieldtype": "Link", "options": master},
                update_modified=False,
            )


def _drop_select_property_setters():
    for _master, (_f, _d, targets) in MASTERS.items():
        for doctype, fieldname in targets:
            frappe.db.delete(
                "Property Setter",
                {
                    "doc_type": doctype,
                    "field_name": fieldname,
                    "property": ["in", ["options", "fieldtype"]],
                },
            )
