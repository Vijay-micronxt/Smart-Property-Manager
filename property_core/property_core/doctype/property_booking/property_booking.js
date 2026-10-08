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

		if (frm.doc.docstatus === 2 && frm.doc.refund_status === "Refund Due") {
			frm.add_custom_button(__("Make Refund"), () => make_refund(frm));
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
	property_core.follow_up.create_customer(frm.doc.lead);
}

function make_refund(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Refund on Cancellation"),
		fields: [
			{
				fieldname: "amount",
				fieldtype: "Currency",
				label: __("Refund Amount"),
				default: frm.doc.cancellation_refund,
				reqd: 1,
				description: __("Collected {0}, forfeited {1}", [
					format_currency(frm.doc.cancellation_collected),
					format_currency(frm.doc.cancellation_forfeit),
				]),
			},
			{ fieldname: "mode_of_payment", fieldtype: "Link", options: "Mode of Payment", label: __("Mode of Payment"), reqd: 1 },
			{ fieldname: "posting_date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today() },
			{ fieldname: "reference_no", fieldtype: "Data", label: __("Cheque / UTR No") },
			{ fieldname: "reference_date", fieldtype: "Date", label: __("Cheque / UTR Date") },
		],
		primary_action_label: __("Refund"),
		primary_action(values) {
			frappe.call({
				method: "property_core.property_core.utils.cancellation.make_refund",
				args: { booking: frm.doc.name, ...values },
				freeze: true,
				callback(r) {
					d.hide();
					frappe.show_alert({ message: __("Refunded by {0}", [r.message.payment_entry]), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
