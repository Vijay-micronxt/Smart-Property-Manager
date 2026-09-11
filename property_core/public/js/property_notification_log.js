frappe.ui.form.on("Property Notification Log", {
	refresh(frm) {
		if (frm.doc.status === "Sent") return;

		frm.add_custom_button(__("Retry Now"), () => {
			frappe.call({
				method: "property_core.property_core.doctype.property_notification_log.property_notification_log.retry",
				args: { log_name: frm.doc.name },
				freeze: true,
				freeze_message: __("Re-queueing…"),
				callback: () => {
					frappe.show_alert({ message: __("Re-queued."), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
	},
});
