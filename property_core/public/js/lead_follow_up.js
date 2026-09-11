frappe.ui.form.on("Lead", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			__("Send Follow-Up Reminder"),
			() => {
				frappe.call({
					method:
						"property_core.property_core.notifications.lead_followup.send_follow_up_now",
					args: { lead_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Queueing reminder…"),
					callback: (r) => property_core.notify.report(r, __("Reminder queued")),
				});
			},
			__("Follow-Up")
		);

		frm.add_custom_button(
			__("Reminder History"),
			() => {
				frappe.set_route("List", "Property Notification Log", {
					reference_doctype: "Lead",
					reference_name: frm.doc.name,
				});
			},
			__("Follow-Up")
		);

		if (frm.doc.custom_last_reminder_sent_on) {
			frm.dashboard.add_indicator(
				__("{0} reminder(s), last {1}", [
					frm.doc.custom_follow_up_reminder_count || 0,
					frappe.datetime.comment_when(frm.doc.custom_last_reminder_sent_on),
				]),
				"blue"
			);
		}
	},

	custom_next_follow_up_date(frm) {
		if (!frm.doc.custom_next_follow_up_date) return;
		if (frm.doc.custom_next_follow_up_date < frappe.datetime.get_today()) {
			frappe.show_alert({
				message: __("Follow-up date is in the past — an overdue reminder goes out on the next run."),
				indicator: "orange",
			});
		}
	},
});
