frappe.ui.form.on("Utility Meter", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Utility Bills"), function () {
                frappe.set_route("List", "Utility Bill", { utility_meter: frm.doc.name });
            }, __("View"));

            frm.add_custom_button(__("New Utility Bill"), function () {
                frappe.new_doc("Utility Bill", {
                    utility_meter: frm.doc.name,
                    property_unit: frm.doc.property_unit,
                    customer: frm.doc.customer,
                    rate_per_unit: frm.doc.rate_per_unit,
                });
            }, __("Actions"));
        }
    },
});
