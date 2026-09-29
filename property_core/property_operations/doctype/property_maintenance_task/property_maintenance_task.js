// A maintenance visit: post progress from site with photos, then complete it.
// Completing asks for proof (a photo or file) unless settings say otherwise.

const MNT_METHOD = "property_core.property_operations.doctype.property_maintenance_task.property_maintenance_task.";

frappe.ui.form.on("Property Maintenance Task", {
	refresh(frm) {
		if (frm.is_new()) return;

		const color = { Open: "orange", "In Progress": "blue", Completed: "green", Cancelled: "red" }[frm.doc.status];
		const done = frm.doc.progress ? __(" — {0}% done", [frm.doc.progress]) : "";
		frm.set_intro(__("Status: {0}{1}", [__(frm.doc.status), done]), color);

		const open = !["Completed", "Cancelled"].includes(frm.doc.status);
		if (open) {
			frm.add_custom_button(__("Post Update"), () => post_update(frm)).addClass("btn-primary");
			frm.add_custom_button(__("Mark Completed"), () => complete(frm));
		}
		frm.add_custom_button(__("Unit"), () => frappe.set_route("Form", "Property Unit", frm.doc.property_unit), __("View"));
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Charge"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("View"));
		}
		render_updates(frm);
	},
});

function post_update(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Progress From Site"),
		fields: [
			{ fieldname: "update_type", fieldtype: "Select", label: __("Update"), options: ["Progress", "Blocked", "Note"], default: "Progress", reqd: 1 },
			{ fieldname: "progress", fieldtype: "Percent", label: __("Work Done"), default: frm.doc.progress || 0, depends_on: "eval:doc.update_type != 'Note'" },
			{ fieldname: "note", fieldtype: "Small Text", label: __("What was done"), reqd: 1 },
			{ fieldtype: "HTML", options: `<div class="text-muted small">${__("Save, then attach photos or a clip of the work.")}</div>` },
		],
		primary_action_label: __("Save and attach proof"),
		primary_action: (values) => {
			frappe.call({
				method: MNT_METHOD + "post_update",
				args: { task: frm.doc.name, update_type: values.update_type, note: values.note,
					progress: values.update_type === "Note" ? null : values.progress },
				freeze: true,
				callback: (r) => {
					if (!r.message) return;
					d.hide();
					attach_proof(frm, "Property Maintenance Update", r.message.name);
				},
			});
		},
	});
	d.show();
}

function attach_proof(frm, doctype, docname, after) {
	new frappe.ui.FileUploader({
		doctype, docname,
		allow_multiple: true,
		make_attachments_public: false,
		on_success: () => {
			frappe.show_alert({ message: __("Proof attached"), indicator: "green" });
			after ? after() : frm.reload_doc();
		},
	});
	frm.reload_doc();
}

function complete(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Complete Maintenance"),
		fields: [{ fieldname: "work_done", fieldtype: "Small Text", label: __("What was done"), reqd: 1, default: frm.doc.work_done }],
		primary_action_label: __("Complete"),
		primary_action: (values) => {
			frappe.call({
				method: MNT_METHOD + "complete",
				args: { task: frm.doc.name, work_done: values.work_done },
				freeze: true,
				callback: () => { d.hide(); frm.reload_doc(); },
				error: () => {
					// no proof yet: let them attach it straight to the task, then retry
					d.hide();
					frappe.confirm(__("Attach a photo or file as proof now?"), () =>
						attach_proof(frm, "Property Maintenance Task", frm.doc.name, () =>
							frappe.call({ method: MNT_METHOD + "complete", args: { task: frm.doc.name, work_done: values.work_done },
								callback: () => frm.reload_doc() })));
				},
			});
		},
	});
	d.show();
}

function render_updates(frm) {
	const field = frm.get_field("updates_html");
	if (!field || !field.$wrapper) return;
	frappe.call({
		method: MNT_METHOD + "get_updates",
		args: { task: frm.doc.name },
		callback: (r) => {
			const data = r.message || {};
			const thumbs = (files) => (files || []).map((f) => f.kind === "image"
				? `<a href="${f.file_url}" target="_blank"><img src="${f.file_url}" style="height:72px;width:72px;object-fit:cover;border-radius:4px;margin:4px 4px 0 0"></a>`
				: `<a href="${f.file_url}" target="_blank" class="btn btn-xs btn-default" style="margin:4px 4px 0 0">${frappe.utils.escape_html(f.file_name)}</a>`).join("");
			const rows = (data.updates || []).map((u) => `
				<div style="padding:10px 0;border-bottom:1px solid var(--border-color)">
					<span class="indicator-pill ${u.update_type === "Blocked" ? "red" : "blue"}">${__(u.update_type)}</span>
					${u.update_type !== "Note" ? `<b>${u.progress || 0}%</b>` : ""}
					<span class="text-muted">&middot; ${frappe.datetime.str_to_user(u.posted_on)} &middot; ${frappe.utils.escape_html(u.posted_by_name || "")}</span>
					${u.note ? `<div>${frappe.utils.escape_html(u.note)}</div>` : ""}<div>${thumbs(u.proof)}</div>
				</div>`).join("");
			const task_files = (data.task_files || []).length
				? `<div style="padding:10px 0"><b>${__("Attached to the task")}</b><div>${thumbs(data.task_files)}</div></div>` : "";
			field.$wrapper.html(rows || task_files
				? rows + task_files
				: `<div class="text-muted">${__("Nothing reported from site yet. Use Post Update.")}${data.proof_required ? " " + __("A photo or file is needed before it can be completed.") : ""}</div>`);
		},
	});
}
