// Lead list: work the queue without opening a lead.
//
// JD's CRM Lead list grew a call icon and a WhatsApp icon on every row, bolted
// on with a MutationObserver that re-scanned the DOM every time anything
// moved. This is the same two icons through the list's own formatter, so they
// are drawn once with the row and cannot drift out of step with it.

frappe.provide("property_core");

const ICON_CALL = `<svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">
<path d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.2.4 2.4.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1A17 17 0 0 1 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.4 0 .8-.2 1l-2.3 2.2z"/></svg>`;

const ICON_WHATSAPP = `<svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">
<path d="M12 2a10 10 0 0 0-8.6 15l-1.3 4.7 4.8-1.3A10 10 0 1 0 12 2zm0 2a8 8 0 1 1-4.1 14.9l-.4-.2-2.5.7.7-2.4-.3-.4A8 8 0 0 1 12 4zm-3.4 4c-.2 0-.5.1-.7.4-.2.3-.8.8-.8 1.9s.8 2.2.9 2.4c.1.2 1.6 2.6 4 3.5 2 .8 2.4.6 2.8.6.4 0 1.4-.6 1.6-1.1.2-.6.2-1 .1-1.1l-.6-.3c-.2-.1-1.2-.6-1.4-.7-.2-.1-.4-.1-.5.1l-.7.9c-.1.2-.3.2-.5.1-.2-.1-1-.4-1.8-1.2-.7-.6-1.1-1.4-1.2-1.6-.1-.2 0-.4.1-.5l.4-.4.2-.4v-.4c0-.1-.5-1.3-.7-1.8-.2-.4-.4-.4-.5-.4h-.4z"/></svg>`;

function icon_button(cls, doc, number, title, icon, colour) {
	return `<button class="btn btn-xs ${cls}"
		data-lead="${frappe.utils.escape_html(doc.name)}"
		data-number="${frappe.utils.escape_html(number)}"
		data-title="${frappe.utils.escape_html(doc.lead_name || doc.name)}"
		title="${title}"
		style="background:${colour};color:#fff;border:none;padding:2px 6px;border-radius:3px;margin-left:4px;line-height:1">
		${icon}</button>`;
}

frappe.listview_settings["Lead"] = frappe.listview_settings["Lead"] || {};

Object.assign(frappe.listview_settings["Lead"], {
	add_fields: ["mobile_no", "lead_name", "custom_lead_status", "custom_next_follow_up_date"],

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

	formatters: {
		mobile_no(value, df, doc) {
			if (!value) return "";
			const number = frappe.utils.escape_html(value);
			return `<span class="lead-contact-cell">${number}
				${icon_button("lead-call-btn", doc, value, __("Call"), ICON_CALL, "#5e64ff")}
				${icon_button("lead-wa-btn", doc, value, __("WhatsApp"), ICON_WHATSAPP, "#25D366")}
			</span>`;
		},
	},

	onload(listview) {
		// Delegated, so rows rendered later are covered without re-scanning.
		listview.$result
			.off("click.property_core")
			.on("click.property_core", ".lead-call-btn, .lead-wa-btn", function (event) {
				event.preventDefault();
				event.stopPropagation();

				const $btn = $(this);
				const lead = $btn.data("lead");
				const number = String($btn.data("number"));
				const title = $btn.data("title");

				if ($btn.hasClass("lead-call-btn")) {
					property_core.follow_up.call("Lead", lead, number);
				} else {
					property_core.follow_up.whatsapp_dialog("Lead", lead, number, title);
				}
			});
	},
});
