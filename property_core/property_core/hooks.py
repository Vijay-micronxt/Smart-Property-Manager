app_name = "property_core"
app_title = "Property Core"
app_publisher = "Smart Property Manager"
app_description = "Property Lifecycle Core - Inventory, Booking, Allocation, Agreement"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = []
app_include_css = []

doctype_js = {
    "Property": "public/js/property.js",
    "Property Unit": "public/js/property_unit.js",
    "Payment Plan": "public/js/payment_plan.js",
    "Property Allocation": "public/js/property_allocation.js",
    "Property Agreement": "public/js/property_agreement.js",
}

scheduler_events = {
    "daily": [
        "property_core.property_core.utils.billing_engine.run_daily_billing",
    ]
}

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
