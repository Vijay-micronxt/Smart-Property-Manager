frappe.ui.form.on("Inspection Checklist", {
    refresh(frm) {
        if (frm.doc.checklist_items && frm.doc.checklist_items.length === 0) {
            frm.add_custom_button(__("Load Default Items"), function () {
                frappe.call({
                    method: "property_operations.property_operations.property_operations.doctype.inspection_checklist.inspection_checklist.get_default_items",
                    callback(r) {
                        if (r.message) {
                            r.message.forEach(row => frm.add_child("checklist_items", row));
                            frm.refresh_field("checklist_items");
                            frappe.show_alert({ message: __("Default items loaded"), indicator: "green" });
                        }
                    },
                });
            }, __("Actions"));
        }
    },
});
