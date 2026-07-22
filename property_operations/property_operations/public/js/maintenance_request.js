frappe.ui.form.on("Maintenance Request", {
    refresh(frm) {
        if (!frm.is_new() && !frm.doc.work_order && frm.doc.status !== "Closed") {
            frm.add_custom_button(__("Create Work Order"), function () {
                frappe.new_doc("Work Order", {
                    maintenance_request: frm.doc.name,
                    property_unit: frm.doc.property_unit,
                    description: frm.doc.description,
                });
            }, __("Actions"));
        }

        if (frm.doc.work_order) {
            frm.add_custom_button(__("View Work Order"), function () {
                frappe.set_route("Form", "Work Order", frm.doc.work_order);
            }, __("View"));
        }

        const color = {
            "Open": "orange",
            "Assigned": "blue",
            "In Progress": "blue",
            "Resolved": "green",
            "Closed": "green",
        }[frm.doc.status] || "gray";

        if (!frm.is_new()) {
            frm.set_intro(__("Status: {0}", [frm.doc.status]), color);
        }
    },

    property_unit(frm) {
        if (frm.doc.property_unit) {
            frappe.db.get_value("Property Unit", frm.doc.property_unit, "customer", (r) => {
                if (r && r.customer) frm.set_value("customer", r.customer);
            });
        }
    },
});
