frappe.ui.form.on("Payment Plan", {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.payment_status === "Pending" && !frm.doc.invoice) {
            frm.add_custom_button(__("Generate Invoice"), function () {
                frappe.confirm(
                    __("Generate a Sales Invoice for milestone <b>{0}</b> of {1}?",
                        [frm.doc.milestone, format_currency(frm.doc.amount)]),
                    function () {
                        frappe.call({
                            method: "property_core.property_core.doctype.payment_plan.payment_plan.generate_invoice",
                            args: { payment_plan_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Generating Invoice..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: __("Invoice {0} created", [
                                            `<a href='/app/sales-invoice/${r.message}'>${r.message}</a>`
                                        ]),
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Actions"));
        }

        if (frm.doc.invoice) {
            frm.add_custom_button(__("View Invoice"), function () {
                frappe.set_route("Form", "Sales Invoice", frm.doc.invoice);
            }, __("Actions"));
        }
    }
});
