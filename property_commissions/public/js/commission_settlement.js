frappe.ui.form.on("Commission Settlement", {
    refresh(frm) {
        if (frm.doc.docstatus === 0 && frm.doc.sales_person) {
            frm.add_custom_button(__("Load Pending Entries"), function () {
                frappe.call({
                    method: "property_commissions.property_commissions.property_commissions.doctype.commission_settlement.commission_settlement.get_pending_entries",
                    args: { sales_person: frm.doc.sales_person },
                    callback(r) {
                        if (!r.message || !r.message.length) {
                            frappe.msgprint(__("No pending commission entries found for this Sales Person."));
                            return;
                        }
                        r.message.forEach(row => {
                            frm.add_child("commission_entries", {
                                commission_entry: row.name,
                                booking: row.booking,
                                property_unit: row.property_unit,
                                commission_amount: row.commission_amount,
                                commission_date: row.commission_date,
                            });
                        });
                        frm.refresh_field("commission_entries");
                        _recalc_total(frm);
                        frappe.show_alert({ message: __("{0} entries loaded", [r.message.length]), indicator: "green" });
                    },
                });
            }, __("Actions"));
        }
    },

    sales_person(frm) {
        if (frm.doc.commission_entries && frm.doc.commission_entries.length) {
            frm.clear_table("commission_entries");
            frm.refresh_field("commission_entries");
            frm.set_value("total_amount", 0);
        }
    },
});

frappe.ui.form.on("Commission Settlement Entry", {
    commission_amount(frm) { _recalc_total(frm); },
    commission_entries_remove(frm) { _recalc_total(frm); },
});

function _recalc_total(frm) {
    const total = (frm.doc.commission_entries || []).reduce(
        (sum, row) => sum + (row.commission_amount || 0), 0
    );
    frm.set_value("total_amount", total);
}
