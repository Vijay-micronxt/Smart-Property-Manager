// Collect an outstanding invoice online: staff pick the gateway (Pay by
// Razorpay / mSwipe / any added by hook), get a payment link and send it.
// Same API as the customer portal and the CRM app: api.payments.options/start.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || flt(frm.doc.outstanding_amount) <= 0) return;
		frm.add_custom_button(__("Collect Online"), () => collect_online(frm), __("Notify"));
	},
});

function collect_online(frm) {
	frappe.call({
		method: "property_core.api.payments.options",
		args: { target: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const o = (r.message && r.message.data) || {};
			const gateways = (o.gateways || []).filter((g) => g.modes.includes("link"));
			if (!gateways.length) {
				frappe.msgprint({
					title: __("No online payment gateway"),
					indicator: "orange",
					message: __(
						"Enable Razorpay or mSwipe (fill in its Settings) to send payment links."
					),
				});
				return;
			}
			const due = (o.due && o.due.amount) || frm.doc.outstanding_amount;
			const d = new frappe.ui.Dialog({
				title: __("Collect Online"),
				fields: [
					{
						fieldname: "gateway",
						fieldtype: "Select",
						label: __("Pay by"),
						options: gateways.map((g) => g.name),
						default: gateways[0].name,
						reqd: 1,
					},
					{
						fieldname: "amount",
						fieldtype: "Currency",
						label: __("Amount"),
						default: due,
						reqd: 1,
						description: __("Due now: {0}", [format_currency(due, frm.doc.currency)]),
					},
				],
				primary_action_label: __("Create Payment Link"),
				primary_action(values) {
					frappe.call({
						method: "property_core.api.payments.start",
						args: {
							target: frm.doc.name,
							amount: values.amount,
							mode: "link",
							gateway: values.gateway,
						},
						freeze: true,
						freeze_message: __("Creating link…"),
						callback: (res) => {
							d.hide();
							show_link((res.message && res.message.data) || {});
						},
					});
				},
			});
			d.show();
		},
	});
}

function show_link(data) {
	const url = data.link && data.link.url;
	if (!url) return;
	const d = new frappe.ui.Dialog({
		title: __("{0} payment link", [data.gateway]),
		fields: [{ fieldname: "html", fieldtype: "HTML" }],
		primary_action_label: __("Copy Message"),
		primary_action() {
			frappe.utils.copy_to_clipboard(data.share_text || url);
		},
	});
	d.fields_dict.html.$wrapper.html(`
		<p><a href="${encodeURI(url)}" target="_blank" rel="noopener">${frappe.utils.escape_html(url)}</a></p>
		<p class="text-muted">${frappe.utils.escape_html(data.share_text || "")}</p>
		<a class="btn btn-default btn-sm" target="_blank" rel="noopener"
			href="https://wa.me/?text=${encodeURIComponent(data.share_text || url)}">${__("Share on WhatsApp")}</a>
		<p class="text-muted small" style="margin-top:10px">${__(
			"The payment is recorded on this invoice automatically once the customer pays."
		)}</p>`);
	d.show();
}
