frappe.ui.form.on("Paytm Settings", {
	refresh(frm) {
		frm.fields_dict["merchant_id"]?.$input?.attr("autocomplete", "off");
		frm.fields_dict["merchant_key"]?.$input?.attr("autocomplete", "new-password");
	},
});
