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

// Walk-in path: a customer standing in front of the layout picks a unit and
// books it there. The Opportunity route stays the primary one, this is the
// shortcut for deals that never had a pipeline stage.
frappe.ui.form.on("Property Unit", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (["Available", "Reserved"].includes(frm.doc.availability_status)) {
			frm.add_custom_button(
				__("Property Booking"),
				() =>
					frappe.model.open_mapped_doc({
						method:
							"property_core.property_core.doctype.property_booking.property_booking.make_from_property_unit",
						frm: frm,
					}),
				__("Create")
			);
		}

		frm.add_custom_button(
			__("Bookings"),
			() => frappe.set_route("List", "Property Booking", { property_unit: frm.doc.name }),
			__("View")
		);

		frm.add_custom_button(
			__("Interested Leads"),
			() => frappe.set_route("List", "Lead", { custom_property_unit: frm.doc.name }),
			__("View")
		);
	},
});
