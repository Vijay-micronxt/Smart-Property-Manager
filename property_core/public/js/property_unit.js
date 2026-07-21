frappe.ui.form.on("Property Unit", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("New Booking"), function () {
                frappe.new_doc("Property Booking", { property_unit: frm.doc.name });
            }, __("Create"));

            if (frm.doc.availability_status === "Available") {
                frm.set_intro(__("This unit is available for booking."), "green");
            } else {
                frm.set_intro(
                    __("Status: {0}", [frm.doc.availability_status]),
                    frm.doc.availability_status === "Booked" ? "orange" : "red"
                );
            }
        }

        if (!frm.doc.item_code) {
            frm.set_df_property("item_code", "description",
                "⚠️ Set an ERPNext Item here before generating invoices. " +
                "Create an Item named 'Plot', 'Flat', etc. in ERPNext first."
            );
        }
    }
});
