from frappe import _


def get_data():
    return {
        "fieldname": "property",
        "non_standard_fieldnames": {
            "Property Booking": "unit_property",
            "Opportunity": "custom_property",
            "Lead": "custom_property",
        },
        # Property Agreement and Property Allocation are deliberately absent:
        # both hang off the unit, not the development, and neither carries a
        # `property` column -- listing them here made opening a Property throw
        # "Unknown column". They are on the Property Unit dashboard instead.
        "transactions": [
            {"label": _("Inventory"), "items": ["Property Unit"]},
            {"label": _("Sales"), "items": ["Lead", "Opportunity", "Property Booking"]},
        ],
    }
