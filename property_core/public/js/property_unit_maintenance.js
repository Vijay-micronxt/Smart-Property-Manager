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
					"property_core.property_operations.utils.maintenance_schedule.bill_now",
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

		frm.add_custom_button(__("Open Due Maintenance Tasks"), () => {
			frappe.call({
				method: "property_core.property_operations.utils.maintenance_tasks.generate_now",
				args: { property_unit: frm.doc.name },
				freeze: true,
				callback: (r) => {
					const n = ((r.message || {}).created || []).length;
					frappe.show_alert({ message: n ? __("{0} task(s) opened", [n]) : __("No visit due yet"), indicator: n ? "green" : "blue" });
					render_maintenance_schedule(frm);
				},
			});
		}, __("Maintenance"));
		frm.add_custom_button(__("New Maintenance Task"), () =>
			frappe.new_doc("Property Maintenance Task", { property_unit: frm.doc.name, source: "Manual" }), __("Maintenance"));
	},
});

const TASK_STATUS_COLOR = { Open: "orange", "In Progress": "blue", Completed: "green", Cancelled: "gray" };

// What was actually done on the unit, visit by visit, next to what was charged.
function render_maintenance_tasks(frm, $wrapper) {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Property Maintenance Task",
			filters: { property_unit: frm.doc.name },
			fields: ["name", "subject", "scheduled_date", "status", "progress", "assigned_to", "completed_on"],
			order_by: "scheduled_date desc",
			limit_page_length: 50,
		},
		callback(r) {
			const rows = r.message || [];
			const body = rows.map((t) => `
				<tr>
					<td><a href="/app/property-maintenance-task/${t.name}">${frappe.utils.escape_html(t.subject || t.name)}</a></td>
					<td>${frappe.datetime.str_to_user(t.scheduled_date)}</td>
					<td><span class="indicator-pill ${TASK_STATUS_COLOR[t.status] || "gray"}">${__(t.status)}</span></td>
					<td>${t.progress || 0}%</td>
					<td>${frappe.utils.escape_html(t.assigned_to || "")}</td>
					<td>${t.completed_on ? frappe.datetime.str_to_user(t.completed_on) : ""}</td>
				</tr>`).join("");
			$wrapper.append(`
				<div style="margin-top:14px"><b>${__("Maintenance work")}</b></div>
				${rows.length ? `<div style="overflow-x:auto"><table class="table table-bordered" style="margin:6px 0 0">
					<thead><tr><th>${__("Task")}</th><th>${__("Date")}</th><th>${__("Status")}</th><th>${__("Done")}</th><th>${__("Assigned")}</th><th>${__("Completed")}</th></tr></thead>
					<tbody>${body}</tbody></table></div>`
				: `<div class="text-muted">${__("No maintenance task yet. One opens a few days before each maintenance date.")}</div>`}`);
		},
	});
}

function render_maintenance_schedule(frm) {
	const $wrapper = frm.get_field("maintenance_billing_history").$wrapper;
	$wrapper.html(`<div class="text-muted">${__("Loading...")}</div>`);

	frappe.call({
		method:
			"property_core.property_operations.utils.maintenance_schedule.unit_schedule",
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
				render_maintenance_tasks(frm, $wrapper);
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
			render_maintenance_tasks(frm, $wrapper);
		},
	});
}
