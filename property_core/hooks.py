from property_core.property_core.customer_kyc import CUSTOMER_KYC_FIELDS

app_name = "property_core"
app_title = "Smart Property Manager"
app_publisher = "Smart Property Manager"
app_description = "Property Lifecycle Management — Inventory, Booking, Operations, and Commissions"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = ["/assets/property_core/js/notification_result.js"]
app_include_css = []

add_to_apps_screen = [
    {
        "name": "property_core",
        "logo": "/assets/property_core/images/property-logo.svg",
        "title": "Smart Property Manager",
        "route": "/app/property-core",
    }
]

doctype_js = {
    # property_core module
    "Property": "public/js/property.js",
    "Property Unit": [
        "public/js/property_unit.js",
        "public/js/property_unit_maintenance.js",
    ],
    "Payment Plan": "public/js/payment_plan.js",
    "Property Allocation": "public/js/property_allocation.js",
    "Property Agreement": "public/js/property_agreement.js",
    "Customer": "public/js/customer_kyc.js",
    "Razorpay Settings": "public/js/razorpay_settings.js",
    "Mswipe Settings": "public/js/mswipe_settings.js",
    "Paytm Settings": "public/js/paytm_settings.js",
    # property_operations module
    "Issue": "public/js/issue_work_order.js",
    "Work Order": "public/js/work_order.js",
    "Inspection Checklist": "public/js/inspection_checklist.js",
    "Utility Meter": "public/js/utility_meter.js",
    "Utility Bill": "public/js/utility_bill.js",
    # property_commissions module
    "Commission Rule": "public/js/commission_rule.js",
    "Commission Entry": "public/js/commission_entry.js",
    "Commission Settlement": "public/js/commission_settlement.js",
    # notifications
    "Sales Invoice": "public/js/sales_invoice_notifications.js",
    "Payment Entry": "public/js/payment_entry_notifications.js",
    "Lead": "public/js/lead_follow_up.js",
    "Property Notification Log": "public/js/property_notification_log.js",
}

scheduler_events = {
    "daily": [
        "property_core.property_core.utils.billing_engine.run_daily_billing",
        "property_core.property_core.utils.payment_plan_billing.run_daily_payment_plan_billing",
        "property_core.property_operations.utils.maintenance_billing.run_daily_maintenance_billing",
        "property_core.property_core.notifications.payment_reminders.run_daily_payment_reminders",
        "property_core.property_core.notifications.lead_followup.run_daily_lead_follow_ups",
        "property_core.property_core.notifications.dispatcher.retry_failed",
        "property_core.property_core.notifications.dispatcher.purge_old_logs",
    ]
}

doc_events = {
    "Property Booking": {
        "on_submit": [
            "property_core.property_core.doctype.property_booking.property_booking.on_submit",
            "property_core.property_commissions.doctype.commission_entry.commission_entry.create_commission_entry",
        ],
        "on_cancel": [
            "property_core.property_core.doctype.property_booking.property_booking.on_cancel",
            "property_core.property_commissions.doctype.commission_entry.commission_entry.cancel_commission_entry",
        ],
    },
    "Property Allocation": {
        "on_submit": "property_core.property_core.doctype.property_allocation.property_allocation.on_submit",
        "on_cancel": "property_core.property_core.doctype.property_allocation.property_allocation.on_cancel",
    },
    "Work Order": {
        "on_update": "property_core.property_operations.doctype.work_order.work_order.on_update",
    },
    "Sales Invoice": {
        "on_submit": "property_core.property_core.notifications.invoice.on_submit",
    },
    "Payment Entry": {
        "validate": "property_core.property_core.notifications.receipts.validate",
        "on_submit": "property_core.property_core.notifications.receipts.on_submit",
    },
    "Lead": {
        "on_update": "property_core.property_core.notifications.lead_followup.on_lead_update",
    },
}

custom_fields = {
    "Customer": CUSTOMER_KYC_FIELDS,
}

after_migrate = [
    "property_core.property_core.customer_kyc.sync_customer_kyc_fields",
    "property_core.property_core.crm_links.sync_crm_link_fields",
    "property_core.property_operations.issue_links.sync_issue_link_fields",
    "property_core.property_operations.property_unit_links.sync_property_unit_link_fields",
    "property_core.property_core.notifications.custom_fields.sync_notification_fields",
    "property_core.property_core.doctype.property_notification_settings.property_notification_settings.seed_default_reminder_rules",
]

before_uninstall = [
    "property_core.property_core.customer_kyc.delete_customer_kyc_fields",
    "property_core.property_core.crm_links.delete_crm_link_fields",
    "property_core.property_operations.issue_links.delete_issue_link_fields",
    "property_core.property_operations.property_unit_links.delete_property_unit_link_fields",
    "property_core.property_core.notifications.custom_fields.delete_notification_fields",
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
    {"dt": "Workspace", "filters": [["name", "in", [
        "Property Core",
        "Property Operations",
        "Property Commissions",
    ]]]},
]
