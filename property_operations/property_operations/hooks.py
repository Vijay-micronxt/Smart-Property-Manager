app_name = "property_operations"
app_title = "Property Operations"
app_publisher = "Smart Property Manager"
app_description = "Property Maintenance, Work Orders, Inspections and Utility Tracking"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = []
app_include_css = []

doctype_js = {
    "Maintenance Request": "public/js/maintenance_request.js",
    "Work Order": "public/js/work_order.js",
    "Inspection Checklist": "public/js/inspection_checklist.js",
    "Utility Meter": "public/js/utility_meter.js",
    "Utility Bill": "public/js/utility_bill.js",
}

doc_events = {
    "Work Order": {
        "on_update": "property_operations.property_operations.doctype.work_order.work_order.on_update",
    },
}

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Operations User"]]]},
]
