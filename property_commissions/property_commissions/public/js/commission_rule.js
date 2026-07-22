frappe.ui.form.on("Commission Rule", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Commission Entries"), function () {
                frappe.set_route("List", "Commission Entry", { commission_rule: frm.doc.name });
            }, __("View"));
        }
    },

    commission_type(frm) {
        frm.set_df_property(
            "commission_rate",
            "description",
            frm.doc.commission_type === "Percentage"
                ? __("Percentage of booking amount (e.g. 2 for 2%)")
                : __("Fixed amount per booking")
        );
    },
});
