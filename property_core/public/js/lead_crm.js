// Lead form: the sales-desk behaviour that used to live on Frappe CRM's
// CRM Lead — WhatsApp, click-to-call, follow-up trail, duplicate warning.
// Conversion itself stays native (Create > Opportunity), which is the whole
// reason this moved onto Lead.

frappe.ui.form.on("Lead", {
	refresh(frm) {
		property_core.follow_up.render(frm, "custom_follow_up_history");
		add_contact_actions(frm);
		show_derived_status(frm);
		add_property_actions(frm);
	},

	custom_lead_status(frm) {
		show_derived_status(frm);
	},

	mobile_no(frm) {
		warn_on_duplicate(frm);
	},

	custom_property(frm) {
		frm.set_query("custom_property_unit", () => ({
			filters: {
				property: frm.doc.custom_property,
				availability_status: ["in", ["Available", "Reserved"]],
			},
		}));
		if (frm.doc.custom_property_unit) frm.set_value("custom_property_unit", null);
	},
});

function add_contact_actions(frm) {
	if (frm.is_new() || !frm.doc.mobile_no) return;

	frm.add_custom_button(
		__("WhatsApp"),
		() =>
			property_core.follow_up.whatsapp_dialog(
				"Lead",
				frm.doc.name,
				frm.doc.mobile_no,
				frm.doc.lead_name
			),
		__("Contact")
	);

	frm.add_custom_button(
		__("Call"),
		() => property_core.follow_up.call("Lead", frm.doc.name, frm.doc.mobile_no),
		__("Contact")
	);

	frm.add_custom_button(
		__("Log Follow Up"),
		() => property_core.follow_up.dialog(frm, "custom_follow_up_history"),
		__("Contact")
	);
}

function add_property_actions(frm) {
	if (frm.is_new()) return;

	frm.set_query("custom_property_unit", () => ({
		filters: frm.doc.custom_property
			? { property: frm.doc.custom_property }
			: {},
	}));
}

// The native status is derived from the sales status, so say so out loud
// rather than leaving a greyed-out field people wonder about.
function show_derived_status(frm) {
	if (!frm.doc.custom_lead_status) return;
	frm.dashboard.clear_headline();
	frm.dashboard.set_headline(
		__("Sales status <b>{0}</b> — tracked by the system as <b>{1}</b>", [
			frm.doc.custom_lead_status,
			frm.doc.status || "Open",
		])
	);
}

function warn_on_duplicate(frm) {
	if (!frm.doc.mobile_no || String(frm.doc.mobile_no).replace(/[^0-9]/g, "").length < 10) return;

	frappe.call({
		method: "property_core.property_core.crm.lead_events.find_duplicates",
		args: { mobile_no: frm.doc.mobile_no, exclude: frm.doc.name },
		callback: (r) => {
			const rows = r.message || [];
			if (!rows.length) return;
			const list = rows
				.map(
					(d) =>
						`<li><a href="/app/lead/${encodeURIComponent(d.name)}">${frappe.utils.escape_html(
							d.lead_name || d.name
						)}</a> — ${frappe.utils.escape_html(d.custom_lead_status || "")} (${
							frappe.utils.escape_html(d.lead_owner || "")
						})</li>`
				)
				.join("");
			frm.dashboard.clear_comment();
			frm.dashboard.add_comment(
				`${__("This number already exists on:")}<ul>${list}</ul>`,
				"orange",
				true
			);
		},
	});
}
