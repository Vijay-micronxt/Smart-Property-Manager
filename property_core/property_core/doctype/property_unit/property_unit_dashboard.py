from frappe import _


def get_data():
    return {
        "fieldname": "property_unit",
        "non_standard_fieldnames": {
            "Opportunity": "custom_property_unit",
            "Lead": "custom_property_unit",
        },
        "transactions": [
            {"label": _("Sales"), "items": ["Lead", "Opportunity", "Property Booking"]},
            {"label": _("Handover"), "items": ["Property Agreement", "Property Allocation"]},
            {"label": _("Operations"), "items": ["Issue", "Work Order"]},
        ],
    }
