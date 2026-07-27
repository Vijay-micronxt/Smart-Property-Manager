frappe.ui.form.on("Property Agreement", {
    refresh(frm) {
        const has_deposit = frm.doc.security_deposit_amount > 0;
        const is_active = frm.doc.agreement_status === "Active";
        const deposit_done = frm.doc.security_deposit_received;

        if (!frm.is_new() && has_deposit && is_active && !deposit_done) {
            frm.add_custom_button(__("Record Security Deposit"), function () {
                frappe.confirm(
                    __("Create a Journal Entry for security deposit of <b>₹{0}</b>?",
                        [format_currency(frm.doc.security_deposit_amount)]),
                    function () {
                        frappe.call({
                            method: "property_core.property_core.doctype.property_agreement.property_agreement.record_security_deposit",
                            args: { agreement_name: frm.doc.name },
                            freeze: true,
                            freeze_message: __("Creating Journal Entry..."),
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: __("Journal Entry {0} created", [
                                            `<a href='/app/journal-entry/${r.message}'>${r.message}</a>`
                                        ]),
                                        indicator: "green"
                                    });
                                    frm.reload_doc();
                                }
                            }
                        });
                    }
                );
            }, __("Deposit"));
        }

        if (!frm.is_new() && deposit_done && frm.doc.security_deposit_journal) {
            frm.add_custom_button(__("View Deposit Entry"), function () {
                frappe.set_route("Form", "Journal Entry", frm.doc.security_deposit_journal);
            }, __("Deposit"));

            if (frm.doc.agreement_status === "Terminated") {
                frm.add_custom_button(__("Refund Security Deposit"), function () {
                    frappe.confirm(
                        __("Cancel the deposit Journal Entry {0} to process refund?",
                            [frm.doc.security_deposit_journal]),
                        function () {
                            frappe.call({
                                method: "property_core.property_core.doctype.property_agreement.property_agreement.refund_security_deposit",
                                args: { agreement_name: frm.doc.name },
                                freeze: true,
                                callback(r) {
                                    if (r.message) {
                                        frappe.show_alert({
                                            message: __("Deposit reversed. Process Payment Entry to complete refund."),
                                            indicator: "orange"
                                        });
                                        frm.reload_doc();
                                    }
                                }
                            });
                        }
                    );
                }, __("Deposit"));
            }
        }

        if (frm.doc.security_deposit_received) {
            frm.set_intro(__("Security deposit received and recorded."), "green");
        } else if (has_deposit) {
            frm.set_intro(__("Security deposit of ₹{0} is pending.", [
                format_currency(frm.doc.security_deposit_amount)
            ]), "orange");
        }
    }
});
