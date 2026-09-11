"""JD's CRM Lead customisation, moved onto the ERPNext-native ``Lead``.

Frappe CRM's ``CRM Lead`` has no conversion path into Opportunity, which is
where the real-estate funnel has to go (Lead -> Opportunity -> Property
Booking). So the sales team's status list, source list and property
requirement capture live here instead, on the DocType that already ships the
"Create > Opportunity" action.

The 40 statuses and 60 sources are carried over verbatim -- the team types
these every day and renaming them would be the disruption we are trying to
avoid. Native ``Lead.status`` stays in play underneath: STATUS_MAP collapses
each JD status onto one of ERPNext's nine so set_status(), the Opportunity
conversion and every stock report keep working.

Applied through an after_migrate hook (see hooks.py) -- Frappe does not read
the ``custom_fields`` hooks key on its own, the same reason customer_kyc.py,
crm_links.py and notifications/custom_fields.py push theirs explicitly.
"""

import frappe

# Verbatim from JD's CRM Lead-custom_lead_status.
LEAD_STATUSES = [
    "New",
    "Just Enquired",
    "Interested",
    "Followup",
    "RNR",
    "Not connected",
    "Calls Not connecting",
    "No incoming calls",
    "Number Busy",
    "switched Off",
    "Number Invalid",
    "Call in Future",
    "Under Negotiation",
    "Site Visit Fc",
    "Site Visit Done",
    "Site Visit Follow Up",
    "CP Visit",
    "CP Leads",
    "Channel Partner",
    "Whatsapp",
    "Farm-Stay Enquiry",
    "Looking for Residential",
    "Looking Towards Nelmangala",
    "Checking Other Developers",
    "Different Requirement",
    "Location Mismatch",
    "Lost to Amenities",
    "Lost to location",
    "Lost to Budget",
    "Dropped the Plan",
    "Already Purchased",
    "Not Interested",
    "DND",
    "Junk",
    "Duplicate",
    "vendor",
    "Developer",
    "Agent",
    "Job Enquiry",
    "Booked",
    "converted",
]

# Verbatim from JD's CRM Lead-custom_lead_source.
LEAD_SOURCES = [
    "Farm Land Bazaar",
    "Radisson Event",
    "Nandish Old Data",
    "Leads by Nandish - Meta",
    "Google ads",
    "MAGIC BRICKS",
    "IVR LEADS",
    "IVR",
    "Housing.com",
    "r2c",
    "e2c",
    "Easy2Connect",
    "Leads by Bhoomika",
    "Exotel Call",
    "Viyaan Properties",
    "Shree Shivalaya Real Estate",
    "Manish Anand",
    "CP - Sreeju",
    "CP- Vaibhav",
    "Jitendra - BNI ARKA",
    "Leads By Madhu",
    "Taboola Ads",
    "ABJ",
    "Exotel",
    "JD sir Reference",
    "Magicbrics",
    "Mcube",
    "Napa valley ganesh event",
    "NCC Meadows 2",
    "Google SEO",
    "Ajmera event",
    "Ganeshotsav -  Concorde Napa Valley",
    "Ganeshotsav - SUNCITY",
    "Ganeshotsav - AJMERA INFINITY",
    "Ganeshotsav- PRESTIGE FERNS RESIDENCY",
    "Ganeshotsav -  NCC MEADOWS II",
    "Chess Event (Gopalan Mall)",
    "Linkedin",
    "Instagram",
    "YOUTUBE",
    "PROPHUNT",
    "99 ACRES",
    "OLX",
    "Google Ad",
    "Self Lead",
    "Website",
    "FB",
    "Facebook",
    "BNI",
    "Walk In",
    "Campaign",
    "Customer's Vendor",
    "Leads By Charles",
    "Mass Mailing",
    "Supplier Reference",
    "Exhibition",
    "Cold Calling",
    "Advertisement",
    "Reference",
    "Existing Customer",
    "Whatsapp",
    "Channel Partner",
    "CP Leads",
]

# JD status -> native Lead.status. Anything unlisted falls through to "Open".
STATUS_MAP = {
    "Booked": "Converted",
    "converted": "Converted",
    "Interested": "Interested",
    "Under Negotiation": "Interested",
    "Site Visit Fc": "Interested",
    "Site Visit Done": "Interested",
    "Site Visit Follow Up": "Interested",
    "CP Visit": "Interested",
    "Followup": "Replied",
    "Call in Future": "Replied",
    "Just Enquired": "Replied",
    "Whatsapp": "Replied",
    "CP Leads": "Replied",
    "Channel Partner": "Replied",
    "Farm-Stay Enquiry": "Replied",
    "DND": "Do Not Contact",
    "Junk": "Do Not Contact",
    "Duplicate": "Do Not Contact",
    "Not Interested": "Do Not Contact",
    "Number Invalid": "Do Not Contact",
    "Already Purchased": "Do Not Contact",
    "Dropped the Plan": "Do Not Contact",
    "Lost to Amenities": "Do Not Contact",
    "Lost to location": "Do Not Contact",
    "Lost to Budget": "Do Not Contact",
    "Location Mismatch": "Do Not Contact",
    "Checking Other Developers": "Do Not Contact",
    "Different Requirement": "Do Not Contact",
    "Looking for Residential": "Do Not Contact",
    "Looking Towards Nelmangala": "Do Not Contact",
    "vendor": "Do Not Contact",
    "Developer": "Do Not Contact",
    "Agent": "Do Not Contact",
    "Job Enquiry": "Do Not Contact",
}

# Statuses a plain sales user should not see in the list (JD's rule, kept).
RESTRICTED_STATUSES = [
    "Junk",
    "Not Interested",
    "Just Enquired",
    "Dropped the Plan",
    "Already Purchased",
    "No incoming calls",
    "Number Invalid",
]

UNIT_TYPES = ["Plot", "Flat", "Villa", "Office", "Warehouse", "Shop"]


def _select(values):
    return "\n".join([""] + values)


LEAD_CRM_FIELDS = [
    {
        "fieldname": "custom_lead_status",
        "fieldtype": "Select",
        "label": "Lead Status",
        "options": _select(LEAD_STATUSES),
        "default": "New",
        "reqd": 1,
        "insert_after": "status",
        "in_standard_filter": 1,
        "in_list_view": 1,
        "description": "What the sales team works with. The system status beside it is derived from this.",
    },
    {
        "fieldname": "custom_lead_source",
        "fieldtype": "Select",
        "label": "Lead Source",
        "options": _select(LEAD_SOURCES),
        "default": "Website",
        "reqd": 1,
        "insert_after": "source",
        "in_standard_filter": 1,
        "description": "Mirrored into the native Lead Source link so stock CRM reports keep working.",
    },
    # -- what the prospect actually wants; carried into Opportunity on convert
    {
        "fieldname": "custom_requirement_section",
        "fieldtype": "Section Break",
        "label": "Requirement",
        "insert_after": "custom_property_unit",
        "collapsible": 1,
    },
    {
        "fieldname": "custom_unit_type",
        "fieldtype": "Select",
        "label": "Looking For",
        "options": _select(UNIT_TYPES),
        "insert_after": "custom_requirement_section",
        "in_standard_filter": 1,
    },
    {
        "fieldname": "custom_required_area",
        "fieldtype": "Float",
        "label": "Required Area",
        "insert_after": "custom_unit_type",
    },
    {
        "fieldname": "custom_requirement_col",
        "fieldtype": "Column Break",
        "insert_after": "custom_required_area",
    },
    {
        "fieldname": "custom_budget",
        "fieldtype": "Currency",
        "label": "Budget",
        "insert_after": "custom_requirement_col",
    },
    {
        "fieldname": "custom_preferred_facing",
        "fieldtype": "Select",
        "label": "Preferred Facing",
        "options": _select(
            ["North", "South", "East", "West", "North-East", "North-West", "South-East", "South-West"]
        ),
        "insert_after": "custom_budget",
    },
    # -- follow-up timeline, rendered from Property Follow Up
    {
        "fieldname": "custom_follow_up_tab",
        "fieldtype": "Tab Break",
        "label": "Follow Ups",
        "insert_after": "custom_preferred_facing",
    },
    {
        "fieldname": "custom_follow_up_history",
        "fieldtype": "HTML",
        "label": "Follow Up History",
        "insert_after": "custom_follow_up_tab",
    },
]

OPPORTUNITY_REQUIREMENT_FIELDS = [
    {
        "fieldname": "custom_unit_type",
        "fieldtype": "Select",
        "label": "Looking For",
        "options": _select(UNIT_TYPES),
        "insert_after": "custom_property_unit",
        "in_standard_filter": 1,
    },
    {
        "fieldname": "custom_required_area",
        "fieldtype": "Float",
        "label": "Required Area",
        "insert_after": "custom_unit_type",
    },
    {
        "fieldname": "custom_requirement_col",
        "fieldtype": "Column Break",
        "insert_after": "custom_required_area",
    },
    {
        "fieldname": "custom_budget",
        "fieldtype": "Currency",
        "label": "Budget",
        "insert_after": "custom_requirement_col",
    },
    {
        "fieldname": "custom_preferred_facing",
        "fieldtype": "Select",
        "label": "Preferred Facing",
        "options": _select(
            ["North", "South", "East", "West", "North-East", "North-West", "South-East", "South-West"]
        ),
        "insert_after": "custom_budget",
    },
    {
        "fieldname": "custom_follow_up_tab",
        "fieldtype": "Tab Break",
        "label": "Follow Ups",
        "insert_after": "custom_preferred_facing",
    },
    {
        "fieldname": "custom_follow_up_history",
        "fieldtype": "HTML",
        "label": "Follow Up History",
        "insert_after": "custom_follow_up_tab",
    },
]


def sync_lead_crm_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {"Lead": LEAD_CRM_FIELDS, "Opportunity": OPPORTUNITY_REQUIREMENT_FIELDS},
        ignore_validate=True,
        update=True,
    )
    sync_lead_sources()
    _apply_property_setters()


def sync_lead_sources():
    """Every JD source also exists as a native Lead Source record, so the
    mirrored ``source`` link never fails validation."""
    existing = set(frappe.get_all("Lead Source", pluck="name"))
    for source in LEAD_SOURCES:
        if source in existing:
            continue
        try:
            frappe.get_doc({"doctype": "Lead Source", "source_name": source}).insert(
                ignore_permissions=True
            )
        except frappe.DuplicateEntryError:
            pass


def _apply_property_setters():
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    # Native status is derived, not typed -- show it, do not let anyone edit it.
    make_property_setter("Lead", "status", "read_only", 1, "Check", validate_fields_for_doctype=False)
    make_property_setter(
        "Lead", "status", "label", "System Status", "Data", validate_fields_for_doctype=False
    )
    # Source is mirrored from custom_lead_source; a second dropdown only invites
    # the two to disagree.
    make_property_setter("Lead", "source", "hidden", 1, "Check", validate_fields_for_doctype=False)
    make_property_setter(
        "Lead", "mobile_no", "reqd", 1, "Check", validate_fields_for_doctype=False
    )
    # The list view draws the call and WhatsApp icons into this column.
    make_property_setter(
        "Lead", "mobile_no", "in_list_view", 1, "Check", validate_fields_for_doctype=False
    )
    make_property_setter(
        "Lead",
        "main",
        "search_fields",
        "lead_name,mobile_no,custom_lead_status",
        "Data",
        validate_fields_for_doctype=False,
    )


def delete_lead_crm_fields():
    frappe.db.delete(
        "Custom Field",
        {"dt": "Lead", "fieldname": ["in", [f["fieldname"] for f in LEAD_CRM_FIELDS]]},
    )
    frappe.db.delete(
        "Custom Field",
        {
            "dt": "Opportunity",
            "fieldname": ["in", [f["fieldname"] for f in OPPORTUNITY_REQUIREMENT_FIELDS]],
        },
    )


def apply_lead_status(doc, method=None):
    """Runs after Lead.validate(), so this wins over set_status()."""
    if not doc.get("custom_lead_status"):
        return

    doc.status = STATUS_MAP.get(doc.custom_lead_status, "Open")

    if doc.get("custom_lead_source") and doc.custom_lead_source != doc.get("source"):
        if frappe.db.exists("Lead Source", doc.custom_lead_source):
            doc.source = doc.custom_lead_source
