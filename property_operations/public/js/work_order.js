frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.doc.maintenance_request) {
            frm.add_custom_button(__("Maintenance Request"), function () {
                frappe.set_route("Form", "Maintenance Request", frm.doc.maintenance_request);
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
            frm.set_intro(__("Status: {0}", [frm.doc.status]), color);
        }
    },
});
