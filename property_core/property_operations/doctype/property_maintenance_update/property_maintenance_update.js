frappe.ui.form.on("Property Maintenance Update", {
	refresh(frm) {
		if (frm.doc.maintenance_task) {
			frm.add_custom_button(__("Maintenance Task"), () =>
				frappe.set_route("Form", "Property Maintenance Task", frm.doc.maintenance_task));
		}
	},
});
