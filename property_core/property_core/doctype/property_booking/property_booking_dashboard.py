from frappe import _


def get_data():
    return {
        "fieldname": "booking",
        "non_standard_fieldnames": {
            "Property Follow Up": "reference_name",
            "Property Allocation": "booking",
        },
        "dynamic_links": {"reference_name": ["Property Booking", "reference_doctype"]},
        "transactions": [
            {"label": _("Payments"), "items": ["Payment Plan"]},
            {"label": _("Handover"), "items": ["Property Allocation"]},
            {"label": _("Activity"), "items": ["Property Follow Up"]},
        ],
    }
