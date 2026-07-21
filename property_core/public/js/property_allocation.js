frappe.ui.form.on("Property Allocation", {
    refresh(frm) {
        const is_recurring = ["Lease", "Rental"].includes(frm.doc.allocation_type);

        if (frm.doc.docstatus === 1 && frm.doc.status === "Active" && is_recurring) {
            frm.add_custom_button(__("Rent Invoice Log"), function () {
                frappe.set_route("List", "Rent Invoice Log", { allocation: frm.doc.name });
            }, __("View"));

            if (frm.doc.next_billing_date) {
                frm.dashboard.add_comment(
                    __("Next rent invoice due: <b>{0}</b>", [
                        frappe.datetime.str_to_user(frm.doc.next_billing_date)
                    ]),
                    "blue",
                    true
                );
            }
        }
    },

    allocation_type(frm) {
        const is_recurring = ["Lease", "Rental"].includes(frm.doc.allocation_type);
        frm.toggle_reqd("rent_amount", is_recurring);
        frm.toggle_reqd("billing_frequency", is_recurring);
    }
});
