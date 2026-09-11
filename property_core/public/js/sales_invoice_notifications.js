frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frm.add_custom_button(
			__("Send Invoice"),
			() => {
				frappe.call({
					method: "property_core.property_core.notifications.invoice.send_now",
					args: { invoice_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Queueing invoice…"),
					callback: (r) => property_core.notify.report(r, __("Invoice queued")),
				});
			},
			__("Notify")
		);

		if (flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(
				__("Send Payment Reminder"),
				() => {
					frappe.call({
						method:
							"property_core.property_core.notifications.payment_reminders.send_reminder_now",
						args: { invoice_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Queueing reminder…"),
						callback: (r) => property_core.notify.report(r, __("Reminder queued")),
					});
				},
				__("Notify")
			);
		}

		frm.add_custom_button(
			__("Delivery History"),
			() => {
				frappe.set_route("List", "Property Notification Log", {
					reference_doctype: "Sales Invoice",
					reference_name: frm.doc.name,
				});
			},
			__("Notify")
		);
	},
});
