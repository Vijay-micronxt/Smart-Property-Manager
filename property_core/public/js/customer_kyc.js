frappe.ui.form.on("Customer", {
    refresh(frm) {
        const status = frm.doc.kyc_status;

        if (!frm.is_new()) {
            if (status === "Pending" || !status) {
                frm.add_custom_button(__("Mark KYC Verified"), function () {
                    frappe.confirm(
                        __("Mark KYC as Verified for <b>{0}</b>?", [frm.doc.customer_name]),
                        function () {
                            frappe.call({
                                method: "frappe.client.set_value",
                                args: {
                                    doctype: "Customer",
                                    name: frm.doc.name,
                                    fieldname: {
                                        kyc_status: "Verified",
                                        kyc_verified_on: frappe.datetime.get_today(),
                                        kyc_verified_by: frappe.session.user,
                                    },
                                },
                                callback() {
                                    frm.reload_doc();
                                    frappe.show_alert({ message: __("KYC Verified"), indicator: "green" });
                                }
                            });
                        }
                    );
                }, __("KYC"));

                frm.add_custom_button(__("Reject KYC"), function () {
                    frappe.call({
                        method: "frappe.client.set_value",
                        args: {
                            doctype: "Customer",
                            name: frm.doc.name,
                            fieldname: { kyc_status: "Rejected" },
                        },
                        callback() {
                            frm.reload_doc();
                            frappe.show_alert({ message: __("KYC Rejected"), indicator: "red" });
                        }
                    });
                }, __("KYC"));
            }

            if (status === "Verified") {
                frm.set_intro(
                    __("KYC verified on {0} by {1}.", [
                        frappe.datetime.str_to_user(frm.doc.kyc_verified_on),
                        frm.doc.kyc_verified_by || "—",
                    ]),
                    "green"
                );
            } else if (status === "Rejected") {
                frm.set_intro(__("KYC has been rejected for this customer."), "red");
            } else {
                frm.set_intro(__("KYC verification is pending for this customer."), "orange");
            }
        }
    },
});
