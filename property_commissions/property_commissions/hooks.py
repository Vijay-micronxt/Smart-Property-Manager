app_name = "property_commissions"
app_title = "Property Commissions"
app_publisher = "Smart Property Manager"
app_description = "Sales Commission Rules, Entries and Settlements"
app_email = "admin@smartproperty.com"
app_license = "MIT"

app_include_js = []
app_include_css = []

doctype_js = {
    "Commission Rule": "public/js/commission_rule.js",
    "Commission Entry": "public/js/commission_entry.js",
    "Commission Settlement": "public/js/commission_settlement.js",
}

doc_events = {
    "Property Booking": {
        "on_submit": "property_commissions.property_commissions.doctype.commission_entry.commission_entry.create_commission_entry",
        "on_cancel": "property_commissions.property_commissions.doctype.commission_entry.commission_entry.cancel_commission_entry",
    },
}

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Commission Manager"]]]},
]
