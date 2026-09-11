// WhatsApp / call straight off the Lead list, the way the team works the
// queue today on CRM Lead.

frappe.listview_settings["Lead"] = frappe.listview_settings["Lead"] || {};

Object.assign(frappe.listview_settings["Lead"], {
	add_fields: ["mobile_no", "custom_lead_status", "custom_next_follow_up_date"],

	get_indicator(doc) {
		const dead = [
			"Junk",
			"Duplicate",
			"DND",
			"Not Interested",
			"Number Invalid",
			"Already Purchased",
			"Dropped the Plan",
		];
		const won = ["Booked", "converted"];
		const status = doc.custom_lead_status || doc.status;

		if (won.includes(status)) return [__(status), "green", "custom_lead_status,=," + status];
		if (dead.includes(status)) return [__(status), "red", "custom_lead_status,=," + status];
		if (status === "New") return [__(status), "blue", "custom_lead_status,=," + status];
		return [__(status), "orange", "custom_lead_status,=," + status];
	},

	button: {
		show: (doc) => doc.mobile_no,
		get_label: () => frappe.utils.icon("call", "sm"),
		get_description: (doc) => __("Call {0}", [doc.mobile_no]),
		action: (doc) => property_core.follow_up.call("Lead", doc.name, doc.mobile_no),
	},

	onload(listview) {
		listview.page.add_action_item(__("WhatsApp"), () => {
			const selected = listview.get_checked_items();
			if (selected.length !== 1) {
				frappe.msgprint(__("Pick exactly one lead."));
				return;
			}
			property_core.follow_up.whatsapp(selected[0].mobile_no);
		});
	},
});
