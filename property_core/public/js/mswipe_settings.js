frappe.ui.form.on("Mswipe Settings", {
	refresh(frm) {
		["user_id", "client_id", "cust_code"].forEach(f => {
			frm.fields_dict[f]?.$input?.attr("autocomplete", "off");
		});
		frm.fields_dict["password"]?.$input?.attr("autocomplete", "new-password");
	},
});
