frappe.ui.form.on("Property", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Add Unit"), function () {
                frappe.new_doc("Property Unit", { property: frm.doc.name });
            }, __("Create"));

            frm.add_custom_button(__("View All Units"), function () {
                frappe.set_route("List", "Property Unit", { property: frm.doc.name });
            }, __("View"));

            frm.add_custom_button(__("Layout Editor"), function () {
                frappe.route_options = { property: frm.doc.name };
                frappe.set_route("plot-layout-editor");
            }, __("View"));
        }
    }
});

// Document tree in Frappe Drive. JD had this on Project; it belongs on the
// development the documents are actually about.
frappe.ui.form.on("Property", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Documents"), function () {
            if (frm.doc.drive_folder_id) {
                window.open(`/drive/t/folder/${frm.doc.drive_folder_id}`, "_blank");
                return;
            }
            frappe.call({
                method: "property_core.property_core.utils.drive_folders.create_folders_for_property",
                args: { property_name: frm.doc.name },
                freeze: true,
                freeze_message: __("Building the document folders..."),
                callback: (r) => {
                    if (!r.message) {
                        frappe.msgprint(__("Drive could not create the folders. Check the error log."));
                        return;
                    }
                    frm.reload_doc();
                    window.open(`/drive/t/folder/${r.message}`, "_blank");
                },
            });
        }, __("View"));
    }
});
