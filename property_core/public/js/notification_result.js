frappe.provide("property_core.notify");

// Reports what actually happened per channel. The dispatcher logs a row even
// when a channel is skipped for a missing address, so counting rows would claim
// success when nothing was sent.
property_core.notify.report = function (r, sent_message) {
	const results = (r.message && r.message.results) || [];
	if (!results.length) {
		frappe.msgprint({
			title: __("Nothing Sent"),
			indicator: "red",
			message: __(
				"No channel is enabled. Turn on Email or WhatsApp in Property Notification Settings."
			),
		});
		return;
	}

	const queued = results.filter((x) => x.status === "Queued" || x.status === "Sent");
	const blocked = results.filter((x) => x.status !== "Queued" && x.status !== "Sent");

	if (queued.length) {
		frappe.show_alert({
			message: `${sent_message} (${queued.map((x) => x.channel).join(", ")})`,
			indicator: "green",
		});
	}
	if (blocked.length) {
		frappe.msgprint({
			title: __("Some Channels Did Not Send"),
			indicator: "orange",
			message: blocked
				.map((x) => `<b>${x.channel}</b>: ${frappe.utils.escape_html(x.error || x.status)}`)
				.join("<br>"),
		});
	}
};
