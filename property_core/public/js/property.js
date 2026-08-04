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
