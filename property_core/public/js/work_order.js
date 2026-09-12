// The Work Order is where progress from site lands: a percentage, a note and
// the photos proving it. Billing a maintenance period opens one of these
// automatically, so there is always a record to post against -- and the button
// sits on the form so nobody has to be told which doctype to use.

frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.doc.issue) {
            frm.add_custom_button(__("Issue"), function () {
                frappe.set_route("Form", "Issue", frm.doc.issue);
            }, __("View"));
        }

        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__("Charge"), function () {
                frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
            }, __("View"));
        }

        const color = {
            "Draft": "gray",
            "Assigned": "blue",
            "In Progress": "blue",
            "Completed": "green",
            "Cancelled": "red",
        }[frm.doc.status] || "gray";

        if (!frm.is_new()) {
            const done = frm.doc.progress ? __(" — {0}% done", [frm.doc.progress]) : "";
            frm.set_intro(__("Status: {0}{1}", [frm.doc.status, done]), color);

            if (!["Completed", "Cancelled"].includes(frm.doc.status) || frm.doc.progress < 100) {
                frm.add_custom_button(__("Post Update"), () => post_update(frm)).addClass(
                    "btn-primary"
                );
            }
            render_updates(frm);
        }
    },
});

function post_update(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Progress From Site"),
        fields: [
            {
                fieldname: "update_type",
                fieldtype: "Select",
                label: __("Update"),
                options: ["Progress", "Completed", "Blocked", "Note"],
                default: "Progress",
                reqd: 1,
            },
            {
                fieldname: "progress",
                fieldtype: "Percent",
                label: __("Work Done"),
                default: frm.doc.progress || 0,
                depends_on: "eval:doc.update_type != 'Note'",
            },
            { fieldname: "note", fieldtype: "Small Text", label: __("What was done"), reqd: 1 },
            {
                fieldtype: "HTML",
                fieldname: "hint",
                options: `<div class="text-muted small">${__(
                    "Save this, then attach photos or a clip of the work."
                )}</div>`,
            },
        ],
        primary_action_label: __("Save and attach proof"),
        primary_action: (values) => {
            frappe.call({
                method:
                    "property_core.property_operations.doctype.work_order_update.work_order_update.post_update",
                args: {
                    work_order: frm.doc.name,
                    update_type: values.update_type,
                    progress: values.update_type === "Note" ? null : values.progress,
                    note: values.note,
                },
                freeze: true,
                callback: (r) => {
                    if (!r.message) return;
                    d.hide();
                    attach_proof(frm, r.message.name);
                },
            });
        },
    });
    d.show();
}

// Frappe's own uploader, pointed at the update that was just created -- the
// files land as attachments on it and the portal reads them from there.
function attach_proof(frm, update_name) {
    new frappe.ui.FileUploader({
        doctype: "Work Order Update",
        docname: update_name,
        allow_multiple: true,
        make_attachments_public: false,
        restrictions: { allowed_file_types: ["image/*", "video/*"] },
        on_success: () => {
            frappe.show_alert({ message: __("Proof attached"), indicator: "green" });
            frm.reload_doc();
        },
    });

    // Closing the uploader without a file still leaves a valid update.
    frm.reload_doc();
}

function render_updates(frm) {
    const field = frm.get_field("updates_html");
    if (!field || !field.$wrapper) return;

    frappe.call({
        method:
            "property_core.property_operations.doctype.work_order_update.work_order_update.updates",
        args: { work_order: frm.doc.name },
        callback: (r) => {
            const rows = r.message || [];
            if (!rows.length) {
                field.$wrapper.html(
                    `<div class="text-muted">${__(
                        "Nothing reported from site yet. Use Post Update."
                    )}</div>`
                );
                return;
            }

            field.$wrapper.html(
                rows
                    .map((row) => {
                        const proof = (row.proof || [])
                            .map((file) =>
                                file.kind === "image"
                                    ? `<a href="${file.file_url}" target="_blank"><img src="${file.file_url}"
                                         style="height:72px;width:72px;object-fit:cover;border-radius:4px;margin:4px 4px 0 0"></a>`
                                    : `<a href="${file.file_url}" target="_blank" class="btn btn-xs btn-default"
                                         style="margin:4px 4px 0 0">${frappe.utils.escape_html(file.file_name)}</a>`
                            )
                            .join("");

                        return `<div style="padding:10px 0;border-bottom:1px solid var(--border-color)">
                            <div>
                                <span class="indicator-pill ${
                                    row.update_type === "Blocked" ? "red" : "blue"
                                }">${__(row.update_type)}</span>
                                <b>${row.progress || 0}%</b>
                                <span class="text-muted">&middot; ${frappe.datetime.str_to_user(
                                    row.posted_on
                                )} &middot; ${frappe.utils.escape_html(row.posted_by_name || "")}</span>
                            </div>
                            ${row.note ? `<div>${frappe.utils.escape_html(row.note)}</div>` : ""}
                            <div>${proof}</div>
                        </div>`;
                    })
                    .join("")
            );
        },
    });
}
