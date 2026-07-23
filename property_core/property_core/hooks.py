from property_core.property_core.customer_kyc import CUSTOMER_KYC_FIELDS

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
    "Customer": "public/js/customer_kyc.js",
}

scheduler_events = {
    "daily": [
        "property_core.property_core.utils.billing_engine.run_daily_billing",
        "property_core.property_core.utils.payment_plan_billing.run_daily_payment_plan_billing",
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

custom_fields = {
    "Customer": CUSTOMER_KYC_FIELDS,
}

after_migrate = [
    "property_core.property_core.customer_kyc.sync_customer_kyc_fields",
    "property_core.property_core.crm_links.sync_crm_link_fields",
]

fixtures = [
    {"dt": "Role", "filters": [["name", "in", [
        "Property Manager",
        "Sales User",
        "Operations User",
        "Finance User",
        "Commission Manager",
        "Property Owner",
        "Tenant",
    ]]]},
    {"dt": "Workflow", "filters": [["document_type", "in", [
        "Property Booking",
    ]]]},
    {"dt": "Custom Field", "filters": [["dt", "=", "Customer"], ["fieldname", "like", "kyc_%"]]},
    {"dt": "Custom Field", "filters": [["dt", "=", "Customer"], ["fieldname", "in", [
        "property_kyc_section",
        "property_personal_section",
        "kyc_col_break_1",
        "kyc_col_break_2",
        "id_type",
        "id_number",
        "id_document",
        "date_of_birth",
        "nationality",
        "occupation",
        "annual_income",
        "pan_number",
        "gst_number",
        "address_proof_type",
        "address_proof_document",
    ]]]},
]
