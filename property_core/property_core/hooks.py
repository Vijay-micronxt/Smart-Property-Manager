app_name = "property_core"
app_title = "Property Core"
app_publisher = "Smart Property Manager"
app_description = "Property Lifecycle Core - Inventory, Booking, Allocation, Agreement"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = []
app_include_css = []

doc_events = {
    "Property Booking": {
        "on_submit": "property_core.property_core.doctype.property_booking.property_booking.on_submit",
        "on_cancel": "property_core.property_core.doctype.property_booking.property_booking.on_cancel",
    },
    "Property Allocation": {
        "on_submit": "property_core.property_core.doctype.property_allocation.property_allocation.on_submit",
        "on_cancel": "property_core.property_core.doctype.property_allocation.property_allocation.on_cancel",
    },
}

fixtures = [
    {"dt": "Role", "filters": [["name", "in", [
        "Property Manager",
        "Sales User",
        "Operations User",
        "Finance User",
        "Commission Manager",
    ]]]},
    {"dt": "Workflow", "filters": [["document_type", "in", [
        "Property Booking",
    ]]]},
]
