frappe.ui.form.on("Issue", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.property_unit && !frm.doc.work_order && frm.doc.status !== "Closed") {
			frm.add_custom_button(__("Create Work Order"), () => {
				frappe.new_doc("Work Order", {
					issue: frm.doc.name,
					property_unit: frm.doc.property_unit,
					description: frm.doc.description || frm.doc.subject,
				});
			}, __("Actions"));
		}

		if (frm.doc.work_order) {
			frm.add_custom_button(__("View Work Order"), () => {
				frappe.set_route("Form", "Work Order", frm.doc.work_order);
			}, __("View"));
		}
	},
});
