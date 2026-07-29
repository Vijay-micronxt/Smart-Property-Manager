frappe.ui.form.on("Utility Bill", {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === "Draft" && !frm.doc.invoice) {
            frm.add_custom_button(__("Generate Invoice"), function () {
                frappe.confirm(
                    __("Generate a Sales Invoice for <b>{0}</b> ({1})?", [
                        frm.doc.name,
                        format_currency(frm.doc.amount),
                    ]),
                    function () {
                        frappe.call({
                            method: "property_operations.property_operations.property_operations.doctype.utility_bill.utility_bill.generate_invoice",
                            args: { utility_bill_name: frm.doc.name },
                            callback(r) {
                                if (!r.exc) {
                                    frm.reload_doc();
                                    frappe.show_alert({ message: __("Invoice {0} created", [r.message]), indicator: "green" });
                                }
                            },
                        });
                    }
                );
            }, __("Actions"));
        }

        if (frm.doc.invoice) {
            frm.add_custom_button(__("View Invoice"), function () {
                frappe.set_route("Form", "Sales Invoice", frm.doc.invoice);
            }, __("View"));
        }
    },

    utility_meter(frm) {
        if (frm.doc.utility_meter) {
            frappe.db.get_value(
                "Utility Meter",
                frm.doc.utility_meter,
                ["property_unit", "customer", "rate_per_unit"],
                (r) => {
                    if (r) {
                        frm.set_value("property_unit", r.property_unit);
                        frm.set_value("customer", r.customer);
                        frm.set_value("rate_per_unit", r.rate_per_unit);
                    }
                }
            );
        }
    },

    current_reading(frm) { _update_amount(frm); },
    previous_reading(frm) { _update_amount(frm); },
    rate_per_unit(frm) { _update_amount(frm); },
});

function _update_amount(frm) {
    const consumed = (frm.doc.current_reading || 0) - (frm.doc.previous_reading || 0);
    frm.set_value("units_consumed", Math.max(0, consumed));
    frm.set_value("amount", Math.max(0, consumed) * (frm.doc.rate_per_unit || 0));
}
