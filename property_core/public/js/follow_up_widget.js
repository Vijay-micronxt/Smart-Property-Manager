// Shared follow-up trail + quick actions, mounted on Lead, Opportunity and
// Property Booking. JD had this as a CRM-Lead-only HTML field; here one widget
// serves every stage of the funnel because Property Follow Up is a Dynamic Link.

frappe.provide("property_core.follow_up");

property_core.follow_up = {
	PAGE_LENGTH: 20,

	render(frm, fieldname) {
		const field = frm.get_field(fieldname);
		if (!field || !field.$wrapper) return;
		if (frm.is_new()) {
			field.$wrapper.html(
				`<div class="text-muted">${__("Save this record to start logging follow-ups.")}</div>`
			);
			return;
		}

		const state = (frm.__follow_up_state = frm.__follow_up_state || { start: 0, rows: [] });
		state.start = 0;
		state.rows = [];
		this.fetch(frm, fieldname, state);
	},

	fetch(frm, fieldname, state) {
		frappe.call({
			method:
				"property_core.property_core.doctype.property_follow_up.property_follow_up.get_follow_up_history",
			args: {
				reference_doctype: frm.doctype,
				reference_name: frm.doc.name,
				start: state.start,
				page_length: this.PAGE_LENGTH,
			},
			callback: (r) => {
				if (!r.message) return;
				state.rows = state.rows.concat(r.message.rows || []);
				state.has_more = r.message.has_more;
				state.total = r.message.total;
				state.start = r.message.loaded;
				this.paint(frm, fieldname, state);
			},
		});
	},

	paint(frm, fieldname, state) {
		const field = frm.get_field(fieldname);
		if (!field || !field.$wrapper) return;

		const colour = {
			Open: "orange",
			Completed: "green",
			Rescheduled: "blue",
			Cancelled: "gray",
		};

		const body = state.rows.length
			? state.rows
					.map((row) => {
						const when = frappe.datetime.str_to_user(row.scheduled_on);
						const next = row.next_follow_up_on
							? `<div class="text-muted small">${__("Next")}: ${frappe.datetime.str_to_user(
									row.next_follow_up_on
							  )}${row.next_action ? " &mdash; " + frappe.utils.escape_html(row.next_action) : ""}</div>`
							: "";
						return `
						<div class="d-flex" style="padding:10px 0;border-bottom:1px solid var(--border-color)">
							<div style="flex:1">
								<div>
									<span class="indicator-pill ${colour[row.status] || "gray"}">${__(row.status)}</span>
									<b>${frappe.utils.escape_html(row.follow_up_type)}</b>
									<span class="text-muted">&middot; ${when}</span>
								</div>
								<div class="text-muted small">
									${__("Owner")}: ${frappe.utils.escape_html(row.assigned_to_name || "")}
									${row.outcome ? " &middot; " + __(row.outcome) : ""}
									${row.lead_status_at_follow_up ? " &middot; " + frappe.utils.escape_html(row.lead_status_at_follow_up) : ""}
								</div>
								${row.notes ? `<div>${frappe.utils.escape_html(row.notes)}</div>` : ""}
								${next}
							</div>
							<div><a href="/app/property-follow-up/${encodeURIComponent(row.name)}">${row.name}</a></div>
						</div>`;
					})
					.join("")
			: `<div class="text-muted">${__("No follow-ups logged yet.")}</div>`;

		const more = state.has_more
			? `<button class="btn btn-xs btn-default follow-up-more" style="margin-top:10px">${__(
					"Load more"
			  )} (${state.total - state.rows.length})</button>`
			: "";

		field.$wrapper.html(`
			<div>
				<div class="d-flex justify-content-between align-items-center" style="margin-bottom:8px">
					<b>${__("Follow Ups")} (${state.total || 0})</b>
					<button class="btn btn-xs btn-primary follow-up-add">${__("Log Follow Up")}</button>
				</div>
				${body}
				${more}
			</div>`);

		field.$wrapper.find(".follow-up-add").on("click", () => this.dialog(frm, fieldname));
		field.$wrapper.find(".follow-up-more").on("click", () => this.fetch(frm, fieldname, state));
	},

	dialog(frm, fieldname) {
		const d = new frappe.ui.Dialog({
			title: __("Log Follow Up"),
			fields: [
				{
					fieldname: "follow_up_type",
					fieldtype: "Select",
					label: __("Type"),
					options: ["Call", "WhatsApp", "Email", "Site Visit", "Meeting", "Other"],
					default: "Call",
					reqd: 1,
				},
				{
					fieldname: "outcome",
					fieldtype: "Select",
					label: __("Outcome"),
					options: [
						"",
						"Connected",
						"Not Connected",
						"Callback Requested",
						"Interested",
						"Not Interested",
						"Site Visit Booked",
						"Site Visit Done",
						"Negotiating",
						"Converted",
						"Lost",
					],
				},
				{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
				{ fieldtype: "Column Break" },
				{
					fieldname: "next_follow_up_on",
					fieldtype: "Datetime",
					label: __("Next Follow Up On"),
				},
				{ fieldname: "next_action", fieldtype: "Data", label: __("Next Action") },
				{
					fieldname: "lead_status",
					fieldtype: "Select",
					label: __("Set Lead Status"),
					depends_on: `eval:${frm.doctype === "Lead"}`,
					options: frm.doctype === "Lead" ? frm.get_field("custom_lead_status").df.options : "",
					default: frm.doctype === "Lead" ? frm.doc.custom_lead_status : "",
				},
			],
			primary_action_label: __("Save"),
			primary_action: (values) => {
				frappe.call({
					method:
						"property_core.property_core.doctype.property_follow_up.property_follow_up.log_follow_up",
					args: {
						reference_doctype: frm.doctype,
						reference_name: frm.doc.name,
						follow_up_type: values.follow_up_type,
						outcome: values.outcome,
						notes: values.notes,
						next_follow_up_on: values.next_follow_up_on,
						next_action: values.next_action,
					},
					freeze: true,
					callback: () => {
						d.hide();
						if (frm.doctype === "Lead" && values.lead_status && values.lead_status !== frm.doc.custom_lead_status) {
							frm.set_value("custom_lead_status", values.lead_status).then(() => frm.save());
						} else {
							frm.reload_doc();
						}
						this.render(frm, fieldname);
					},
				});
			},
		});
		d.show();
	},

	// One lead makes one customer, wherever the button is pressed.
	create_customer(lead) {
		frappe.call({
			method: "property_core.property_core.crm.customer_from_lead.make_customer_from_lead",
			args: { lead: lead },
			freeze: true,
			freeze_message: __("Creating customer..."),
			callback: (r) => {
				if (!r.message) return;
				frappe.show_alert({ message: __("Customer {0} ready", [r.message]), indicator: "green" });
				frappe.set_route("Form", "Customer", r.message);
			},
		});
	},

	// Straight to WhatsApp, no template, no dialog.
	whatsapp(number, message) {
		if (!number) {
			frappe.msgprint(__("No mobile number on this record."));
			return;
		}
		const digits = String(number).replace(/[^0-9]/g, "");
		const normalised = digits.length === 10 ? `91${digits}` : digits;
		const text = message ? `?text=${encodeURIComponent(message)}` : "";
		window.open(`https://wa.me/${normalised}${text}`, "_blank");
	},

	// Pick a template, read exactly what will be sent, edit it, send it.
	// The preview comes from the server because the template is rich text and
	// the browser has no business guessing how it collapses to a message.
	whatsapp_dialog(doctype, docname, number, display_name) {
		if (!number) {
			frappe.msgprint(__("No mobile number on this record."));
			return;
		}

		const d = new frappe.ui.Dialog({
			title: __("WhatsApp {0}", [display_name || docname]),
			size: "large",
			fields: [
				{
					fieldname: "template",
					fieldtype: "Link",
					label: __("Template"),
					options: "WhatsApp Message Template",
					get_query: () => ({ filters: { is_active: 1 } }),
					onchange: () => this._load_template(d, doctype, docname, number),
				},
				{ fieldname: "preview", fieldtype: "HTML", label: __("Preview") },
				{ fieldtype: "Section Break" },
				{
					fieldname: "message",
					fieldtype: "Small Text",
					label: __("Message"),
					reqd: 1,
					onchange: () => this._paint_preview(d, number),
				},
			],
			primary_action_label: __("Send"),
			primary_action: (values) => this._send(d, doctype, docname, number, values),
		});

		d.show();
		this._paint_preview(d, number);
	},

	_load_template(d, doctype, docname, number) {
		const template = d.get_value("template");
		if (!template) {
			d.set_value("message", "");
			return;
		}
		frappe.call({
			method: "property_core.property_core.crm.whatsapp.render_template",
			args: { doctype: doctype, docname: docname, template: template },
			freeze: true,
			callback: (r) => {
				d.set_value("message", r.message || "");
				this._paint_preview(d, number);
			},
		});
	},

	_paint_preview(d, number) {
		const field = d.fields_dict.preview;
		if (!field || !field.$wrapper) return;

		const message = d.get_value("message") || "";
		const body = message
			? `<div style="white-space:pre-wrap">${frappe.utils.escape_html(message)}</div>`
			: `<div class="text-muted">${__("Pick a template, or type a message below.")}</div>`;

		field.$wrapper.html(`
			<div style="background:#dcf8c6;color:#111;border-radius:8px;padding:12px 14px;line-height:1.5">
				${body}
				<div style="text-align:right;font-size:11px;opacity:.6;margin-top:8px">${__("To")}: ${frappe.utils.escape_html(
					String(number)
				)}</div>
			</div>`);
	},

	_send(d, doctype, docname, number, values) {
		frappe.call({
			method: "property_core.property_core.crm.whatsapp.send",
			args: {
				doctype: doctype,
				docname: docname,
				phone_number: number,
				message: values.message,
				template: values.template || null,
			},
			freeze: true,
			freeze_message: __("Sending..."),
			callback: (r) => {
				const result = r.message || {};
				d.hide();
				if (result.sent) {
					frappe.show_alert({
						message: __("Sent to {0}", [result.phone || number]),
						indicator: "green",
					});
					if (cur_list) cur_list.refresh();
					return;
				}
				// Not configured, or the gateway refused -- hand it to WhatsApp itself.
				if (result.error) {
					frappe.show_alert({ message: result.error, indicator: "orange" });
				}
				if (result.link) window.open(result.link, "_blank");
			},
		});
	},

	call(doctype, docname, number) {
		if (!number) {
			frappe.msgprint(__("No mobile number on this record."));
			return;
		}
		frappe.call({
			method: "property_core.property_core.crm.telephony.click_to_call",
			args: { to_number: number, reference_doctype: doctype, reference_name: docname },
			freeze: true,
			freeze_message: __("Connecting call..."),
		});
	},
};
