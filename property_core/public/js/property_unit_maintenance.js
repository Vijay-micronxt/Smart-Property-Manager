const MAINTENANCE_STATUS_COLOR = {
	"Paid": "green",
	"Partly Paid": "orange",
	"Unpaid": "orange",
	"Overdue": "red",
	"Draft": "gray",
	"Cancelled": "gray",
	"Return": "gray",
};

frappe.ui.form.on("Property Unit", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.maintenance_plan_template) {
			return;
		}
		render_maintenance_billing_history(frm);
	},
});

function render_maintenance_billing_history(frm) {
	const $wrapper = frm.get_field("maintenance_billing_history").$wrapper;
	$wrapper.html(`<div class="text-muted">${__("Loading...")}</div>`);

	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Sales Invoice",
			filters: {
				property_unit: frm.doc.name,
				maintenance_period: ["is", "set"],
				docstatus: ["!=", 2],
			},
			fields: [
				"name", "maintenance_period", "posting_date", "due_date",
				"grand_total", "outstanding_amount", "status",
			],
			order_by: "posting_date desc",
			limit_page_length: 0,
		},
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				$wrapper.html(`<div class="text-muted">${__("No maintenance invoices generated yet.")}</div>`);
				return;
			}

			let total_billed = 0, total_outstanding = 0;
			const body_rows = rows.map((row) => {
				total_billed += row.grand_total;
				total_outstanding += row.outstanding_amount;
				const paid = row.grand_total - row.outstanding_amount;
				const color = MAINTENANCE_STATUS_COLOR[row.status] || "gray";
				return `
					<tr>
						<td><a href="/app/sales-invoice/${row.name}">${row.maintenance_period}</a></td>
						<td>${frappe.datetime.str_to_user(row.due_date)}</td>
						<td class="text-right">${format_currency(row.grand_total)}</td>
						<td class="text-right">${format_currency(paid)}</td>
						<td class="text-right">${format_currency(row.outstanding_amount)}</td>
						<td><span class="indicator-pill ${color}">${__(row.status)}</span></td>
					</tr>
				`;
			}).join("");

			$wrapper.html(`
				<div class="text-muted small" style="margin-bottom: 8px;">
					${__("Total Billed")}: <b>${format_currency(total_billed)}</b>
					&nbsp;|&nbsp;
					${__("Total Outstanding")}: <b>${format_currency(total_outstanding)}</b>
				</div>
				<table class="table table-bordered" style="margin-bottom: 0;">
					<thead>
						<tr>
							<th>${__("Period")}</th>
							<th>${__("Due Date")}</th>
							<th class="text-right">${__("Amount")}</th>
							<th class="text-right">${__("Paid")}</th>
							<th class="text-right">${__("Outstanding")}</th>
							<th>${__("Status")}</th>
						</tr>
					</thead>
					<tbody>${body_rows}</tbody>
				</table>
			`);
		},
	});
}
