frappe.ui.form.on("Property Allocation", {
    refresh(frm) {
        const is_recurring = ["Lease", "Rental"].includes(frm.doc.allocation_type);

        if (frm.doc.docstatus === 1 && frm.doc.status === "Active" && is_recurring) {
            frm.add_custom_button(__("Rent Invoice Log"), function () {
                frappe.set_route("List", "Rent Invoice Log", { allocation: frm.doc.name });
            }, __("View"));

            frm.add_custom_button(__("Renew Lease"), function () {
                const d = new frappe.ui.Dialog({
                    title: __("Renew Lease"),
                    fields: [
                        {
                            fieldname: "new_end_date",
                            fieldtype: "Date",
                            label: __("New End Date"),
                            reqd: 1,
                        },
                        {
                            fieldname: "escalation_percent",
                            fieldtype: "Float",
                            label: __("Rent Escalation (%)"),
                            description: __("Leave 0 to keep current rent unchanged"),
                            default: 0,
                        },
                    ],
                    primary_action_label: __("Renew"),
                    primary_action(values) {
                        frappe.call({
                            method: "property_core.property_core.property_core.doctype.property_allocation.property_allocation.renew_lease",
                            args: {
                                allocation_name: frm.doc.name,
                                new_end_date: values.new_end_date,
                                escalation_percent: values.escalation_percent || 0,
                            },
                            callback(r) {
                                if (!r.exc) {
                                    d.hide();
                                    frm.reload_doc();
                                    const msg = r.message.escalation_applied
                                        ? __("Lease renewed. New rent: {0}", [format_currency(r.message.new_rent_amount)])
                                        : __("Lease renewed successfully.");
                                    frappe.show_alert({ message: msg, indicator: "green" });
                                }
                            },
                        });
                    },
                });
                d.show();
            }, __("Actions"));

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
