// Every maintenance charge this unit carries — billed, due and upcoming —
// shown the moment the unit has a plan, not once the nightly job has run.
// A freshly booked unit used to say "No maintenance invoices generated yet",
// which told the owner nothing about what they had just signed up for.

const MAINTENANCE_STATUS_COLOR = {
	Billed: "blue",
	Due: "orange",
	Upcoming: "gray",
	Paused: "gray",
};

const INVOICE_STATUS_COLOR = {
	Paid: "green",
	"Partly Paid": "orange",
	Unpaid: "orange",
	Overdue: "red",
	Draft: "gray",
	Cancelled: "gray",
	Return: "gray",
};

frappe.ui.form.on("Property Unit", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.maintenance_plan_template) return;

		render_maintenance_schedule(frm);

		frm.add_custom_button(__("Bill Due Charges Now"), () => {
			frappe.call({
				method:
					"property_core.property_core.property_operations.utils.maintenance_schedule.bill_now",
				args: { property_unit: frm.doc.name },
				freeze: true,
				freeze_message: __("Raising charges..."),
				callback: (r) => {
					const raised = (r.message || {}).raised || 0;
					frappe.show_alert({
						message: raised
							? __("{0} charge(s) raised", [raised])
							: __("Nothing is due yet"),
						indicator: raised ? "green" : "blue",
					});
					render_maintenance_schedule(frm);
				},
			});
		}, __("Maintenance"));
	},
});

function render_maintenance_schedule(frm) {
	const $wrapper = frm.get_field("maintenance_billing_history").$wrapper;
	$wrapper.html(`<div class="text-muted">${__("Loading...")}</div>`);

	frappe.call({
		method:
			"property_core.property_core.property_operations.utils.maintenance_schedule.unit_schedule",
		args: { property_unit: frm.doc.name },
		callback(r) {
			const data = r.message || {};
			const rows = data.schedule || [];

			if (!rows.length) {
				$wrapper.html(
					`<div class="text-muted">${__(
						"This plan has no charges scheduled. Set a Maintenance Start Date, or check the template."
					)}</div>`
				);
				return;
			}

			const body = rows
				.map((row) => {
					const color = MAINTENANCE_STATUS_COLOR[row.status] || "gray";
					const period = row.invoice
						? `<a href="/app/sales-invoice/${row.invoice}">${row.period}</a>`
						: row.period;
					const invoice_state = row.invoice_status
						? `<span class="indicator-pill ${
								INVOICE_STATUS_COLOR[row.invoice_status] || "gray"
						  }">${__(row.invoice_status)}</span>`
						: "";
					return `
						<tr>
							<td>${period}</td>
							<td>${frappe.datetime.str_to_user(row.due_date)}</td>
							<td>${frappe.utils.escape_html(row.description || "")}</td>
							<td class="text-right">${format_currency(row.amount)}</td>
							<td><span class="indicator-pill ${color}">${__(row.status)}</span> ${invoice_state}</td>
						</tr>`;
				})
				.join("");

			$wrapper.html(`
				<div class="text-muted" style="margin-bottom:6px">
					${__("Billed")}: <b>${format_currency(data.total_billed)}</b> &middot;
					${__("Outstanding")}: <b>${format_currency(data.total_outstanding)}</b> &middot;
					${__("Still to come")}: <b>${format_currency(data.total_upcoming)}</b>
				</div>
				<div style="overflow-x:auto">
					<table class="table table-bordered" style="margin:0">
						<thead>
							<tr>
								<th>${__("Period")}</th>
								<th>${__("Due")}</th>
								<th>${__("Charge")}</th>
								<th class="text-right">${__("Amount")}</th>
								<th>${__("Status")}</th>
							</tr>
						</thead>
						<tbody>${body}</tbody>
					</table>
				</div>`);
		},
	});
}
