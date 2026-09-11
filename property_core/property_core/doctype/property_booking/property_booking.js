frappe.ui.form.on("Property Booking", {
	setup(frm) {
		frm.set_query("property_unit", () => ({
			filters: { availability_status: "Available" },
		}));
	},

	refresh(frm) {
		property_core.follow_up.render(frm, "follow_up_history");

		if (frm.is_new()) return;

		if (frm.doc.lead && !frm.doc.customer) {
			frm.dashboard.add_comment(
				__("This booking came from a lead with no customer yet. Create one before submitting."),
				"orange",
				true
			);
			frm.add_custom_button(__("Create Customer from Lead"), () => create_customer(frm));
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Payment Plan"), () =>
				frappe.set_route("List", "Payment Plan", { booking: frm.doc.name })
			);
			frm.add_custom_button(__("Sales Invoices"), () =>
				frappe.set_route("List", "Sales Invoice", { customer: frm.doc.customer })
			);
			if (frm.doc.drive_folder_id) {
				frm.add_custom_button(__("Documents"), () =>
					window.open(`/drive/t/folder/${frm.doc.drive_folder_id}`, "_blank")
				);
			}
		}
	},

	property_unit(frm) {
		if (!frm.doc.property_unit) return;
		frappe.db.get_value("Property Unit", frm.doc.property_unit, "base_price").then((r) => {
			if (r.message && r.message.base_price && !frm.doc.total_price) {
				frm.set_value("total_price", r.message.base_price);
			}
		});
	},
});

function create_customer(frm) {
	frappe.call({
		method: "erpnext.crm.doctype.lead.lead.make_customer",
		args: { source_name: frm.doc.lead },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			const customer = frappe.model.sync(r.message)[0];
			frappe.set_route("Form", "Customer", customer.name);
		},
	});
}
