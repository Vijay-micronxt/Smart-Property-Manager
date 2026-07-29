frappe.ui.form.on("Razorpay Settings", {
	refresh(frm) {
		frm.fields_dict["api_key"]?.$input?.attr("autocomplete", "off");
		["api_secret", "webhook_secret"].forEach(f => {
			frm.fields_dict[f]?.$input?.attr("autocomplete", "new-password");
		});
	},
});
