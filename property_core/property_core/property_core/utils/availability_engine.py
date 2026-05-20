import frappe


BLOCKED_STATUSES = {"Reserved", "Booked", "Allocated", "Leased", "Maintenance Blocked"}


def get_unit_status(unit_name: str) -> str:
    return frappe.db.get_value("Property Unit", unit_name, "availability_status") or "Available"


def assert_unit_available(unit_name: str):
    status = get_unit_status(unit_name)
    if status in BLOCKED_STATUSES:
        frappe.throw(
            frappe._("Property Unit {0} is not available. Current status: {1}").format(
                unit_name, status
            )
        )


def reserve_unit(unit_name: str, customer: str):
    frappe.db.set_value(
        "Property Unit",
        unit_name,
        {"availability_status": "Booked", "customer": customer},
    )


def allocate_unit(unit_name: str, customer: str, allocation_type: str):
    status = "Allocated" if allocation_type == "Sale" else "Leased"
    frappe.db.set_value(
        "Property Unit",
        unit_name,
        {"availability_status": status, "customer": customer},
    )


def release_unit(unit_name: str):
    frappe.db.set_value(
        "Property Unit",
        unit_name,
        {"availability_status": "Available", "customer": None},
    )


def block_unit_for_maintenance(unit_name: str):
    frappe.db.set_value("Property Unit", unit_name, "availability_status", "Maintenance Blocked")
