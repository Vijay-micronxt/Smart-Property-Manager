from frappe import _


def get_data():
    return {
        "fieldname": "property",
        "non_standard_fieldnames": {
            "Property Booking": "unit_property",
            "Opportunity": "custom_property",
            "Lead": "custom_property",
        },
        "transactions": [
            {"label": _("Inventory"), "items": ["Property Unit"]},
            {"label": _("Sales"), "items": ["Lead", "Opportunity", "Property Booking"]},
            {"label": _("Handover"), "items": ["Property Agreement", "Property Allocation"]},
        ],
    }
