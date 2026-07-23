app_name = "property_operations"
app_title = "Property Operations"
app_publisher = "Smart Property Manager"
app_description = "Property Maintenance, Work Orders, Inspections and Utility Tracking"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = []
app_include_css = []

doctype_js = {
    "Issue": "public/js/issue_work_order.js",
    "Work Order": "public/js/work_order.js",
    "Property Unit": "public/js/property_unit_maintenance.js",
    "Inspection Checklist": "public/js/inspection_checklist.js",
    "Utility Meter": "public/js/utility_meter.js",
    "Utility Bill": "public/js/utility_bill.js",
}

doc_events = {
    "Work Order": {
        "on_update": "property_operations.property_operations.doctype.work_order.work_order.on_update",
    },
}

scheduler_events = {
    "daily": [
        "property_operations.property_operations.utils.maintenance_billing.run_daily_maintenance_billing",
    ]
}

after_migrate = [
    "property_operations.property_operations.issue_links.sync_issue_link_fields",
    "property_operations.property_operations.property_unit_links.sync_property_unit_link_fields",
]

before_uninstall = [
    "property_operations.property_operations.issue_links.delete_issue_link_fields",
    "property_operations.property_operations.property_unit_links.delete_property_unit_link_fields",
]

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Operations User"]]]},
]
