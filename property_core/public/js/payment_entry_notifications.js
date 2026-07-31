frappe.ui.form.on("Payment Entry", {
	refresh(frm) {
		const is_customer_receipt =
			frm.doc.payment_type === "Receive" && frm.doc.party_type === "Customer";
		if (!is_customer_receipt) return;

		if (frm.doc.docstatus === 0 && !(frm.doc.references || []).length) {
			frm.add_custom_button(__("Auto-Reconcile"), () => {
				frappe.call({
					method: "property_core.property_core.notifications.receipts.reconcile_now",
					args: { payment_entry_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Matching outstanding invoices…"),
					callback: (r) => {
						frm.reload_doc();
						const res = r.message || {};
						if (res.allocated) {
							frappe.show_alert({
								message: __("Allocated against {0} invoice(s).", [res.allocated]),
								indicator: "green",
							});
						} else {
							frappe.msgprint({
								title: __("Nothing Allocated"),
								indicator: "orange",
								message:
									res.error ||
									__("No outstanding Sales Invoice found for this customer."),
							});
						}
					},
				});
			});
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Send Receipt"),
				() => {
					frappe.call({
						method:
							"property_core.property_core.notifications.receipts.send_receipt_now",
						args: { payment_entry_name: frm.doc.name },
						freeze: true,
						freeze_message: __("Queueing receipt…"),
						callback: (r) =>
							property_core.notify.report(r, __("Receipt queued")),
					});
				},
				__("Notify")
			);

			frm.add_custom_button(
				__("Delivery History"),
				() => {
					frappe.set_route("List", "Property Notification Log", {
						reference_doctype: "Payment Entry",
						reference_name: frm.doc.name,
					});
				},
				__("Notify")
			);
		}

		if (frm.doc.custom_reconciliation_error) {
			frm.dashboard.add_comment(frm.doc.custom_reconciliation_error, "orange", true);
		}
	},
});
