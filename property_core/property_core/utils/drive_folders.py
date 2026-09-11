"""Frappe Drive folder tree for a Property, and a per-booking folder under it.

Ported from JD's "Auto Create Drive Folders on Project" server script. Two
changes from the original:

  * the tree hangs off Property, not Project -- Property is the development
    that documents belong to, and it exists whether or not anyone opened an
    ERPNext Project for construction costing
  * a booking gets its own folder under 06 - Sales & CRM > Booking Documents,
    which is the "folder on booking complete" behaviour JD had bolted onto
    Sales Order

Everything is built inside the caller's transaction, on purpose: the original
hit "Could not find Parent Entity" when the subfolders were queued as a
background job and raced the parent insert.
"""

import frappe

PROPERTY_STRUCTURE = {
    "01 - Land & Legal": [
        "Sale Deeds",
        "RTC - Pahani",
        "Encumbrance Certificate",
        "Mother Deed",
        "Conversion Documents",
        "Tax Paid Receipts",
        "Survey & Measurements",
        "Legal Due Diligence",
        "Title Clearance Reports",
        "JDA - Joint Development Agreements",
    ],
    "02 - Planning & Design": [
        "Concept Planning",
        "Master Layout Plans",
        "Architectural Drawings",
        "Structural Drawings",
        "Electrical Drawings",
        "Plumbing Drawings",
        "Landscape Design",
        "3D Views - Walkthroughs",
        "Soil Testing Reports",
        "BOQ",
    ],
    "03 - Approvals & Compliance": [
        "Layout Approval",
        "RERA Registration",
        "Environmental Clearance",
        "Building Plan Approval",
        "Fire NOC",
        "Electricity & Water NOC",
        "Road Access Approval",
    ],
    "04 - Development & Execution": [
        "Site Photos",
        "Daily Progress Reports",
        "As-Built Drawings",
        "Work Orders",
    ],
    "05 - Procurement & Contracts": [
        "Vendor Agreements",
        "Contractor Agreements",
        "Consultant Agreements",
        "Purchase Orders",
    ],
    "06 - Sales & CRM": [
        "Booking Documents",
        "Sale Agreements",
        "Allotment Letters",
        "Payment Plans",
        "Customer Communications",
    ],
    "07 - Inventory": ["Plot Inventory", "Pricing Matrix"],
    "08 - Quality & Audit": [
        "Site Inspection Reports",
        "Material Testing Reports",
        "Safety Checks",
    ],
    "09 - Handover": [
        "Plot Handover Documents",
        "Completion Certificates",
        "Customer Acceptance Letters",
    ],
}

BOOKING_PARENT_PATH = ("06 - Sales & CRM", "Booking Documents")


def drive_installed():
    return frappe.db.table_exists("Drive File")


def _personal_team(user=None):
    user = user or frappe.session.user
    return frappe.db.get_value("Drive Team", {"owner": user, "personal": 1}, "name")


def _team_root(team):
    return frappe.db.get_value(
        "Drive File",
        {"team": team, "parent_entity": ("is", "not set"), "is_group": 1, "is_active": 1},
        "name",
    )


def get_or_create_folder(title, parent, team):
    existing = frappe.db.get_value(
        "Drive File",
        {"title": title, "is_group": 1, "team": team, "parent_entity": parent, "is_active": 1},
        "name",
    )
    if existing:
        return existing

    folder = frappe.get_doc(
        {
            "doctype": "Drive File",
            "title": title,
            "is_group": 1,
            "mime_type": "frappe_drive/folder",
            "team": team,
            "parent_entity": parent,
            "is_active": 1,
            "is_private": 1,
            "allow_download": 1,
            "_modified": frappe.utils.now(),
        }
    )
    folder.flags.ignore_permissions = True
    folder.insert(ignore_permissions=True)
    return folder.name


def ensure_property_folders(property_name, user=None):
    """Root folder for the property plus the nine-department tree. Returns the
    root folder id, or None when Drive is not usable for this user."""
    if not drive_installed():
        return None

    team = _personal_team(user)
    if not team:
        frappe.log_error(
            f"No personal Drive Team for {user or frappe.session.user}", "Property Drive Setup"
        )
        return None

    root = _team_root(team)
    if not root:
        frappe.log_error(f"No root Drive folder for team {team}", "Property Drive Setup")
        return None

    previous_mute = frappe.flags.get("mute_emails")
    frappe.flags.mute_emails = True
    try:
        property_folder = get_or_create_folder(property_name, root, team)
        frappe.db.set_value(
            "Property", property_name, "drive_folder_id", property_folder, update_modified=False
        )

        for department, subfolders in PROPERTY_STRUCTURE.items():
            department_id = get_or_create_folder(department, property_folder, team)
            for subfolder in subfolders:
                get_or_create_folder(subfolder, department_id, team)

        return property_folder
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Property Drive Setup: {property_name}")
        return None
    finally:
        frappe.flags.mute_emails = previous_mute


def ensure_booking_folder(booking):
    """One folder per booking, under the property's Booking Documents.

    This is JD's "folder on booking complete", moved off Sales Order.
    """
    if not drive_installed() or not booking.get("unit_property"):
        return None

    team = _personal_team()
    if not team:
        return None

    previous_mute = frappe.flags.get("mute_emails")
    frappe.flags.mute_emails = True
    try:
        parent = frappe.db.get_value("Property", booking.unit_property, "drive_folder_id")
        if not parent:
            parent = ensure_property_folders(booking.unit_property)
        if not parent:
            return None

        for segment in BOOKING_PARENT_PATH:
            parent = get_or_create_folder(segment, parent, team)

        # Named for the property and the unit, not the booking id -- that is
        # what people look for when they go hunting for a plot's papers.
        unit_number = (
            frappe.db.get_value("Property Unit", booking.property_unit, "unit_number")
            or booking.property_unit
        )
        title = f"{booking.unit_property} - {unit_number}"
        folder = get_or_create_folder(title, parent, team)
        frappe.db.set_value(
            "Property Booking", booking.name, "drive_folder_id", folder, update_modified=False
        )
        return folder
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Booking Drive Folder: {booking.name}")
        return None
    finally:
        frappe.flags.mute_emails = previous_mute


@frappe.whitelist()
def create_folders_for_property(property_name):
    frappe.has_permission("Property", "write", doc=property_name, throw=True)
    return ensure_property_folders(property_name)
