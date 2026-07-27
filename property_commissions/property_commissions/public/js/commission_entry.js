frappe.ui.form.on("Commission Entry", {
    refresh(frm) {
        if (frm.doc.booking) {
            frm.add_custom_button(__("Property Booking"), function () {
                frappe.set_route("Form", "Property Booking", frm.doc.booking);
            }, __("View"));
        }

        if (frm.doc.settlement) {
            frm.add_custom_button(__("Settlement"), function () {
                frappe.set_route("Form", "Commission Settlement", frm.doc.settlement);
            }, __("View"));
        }

        const color = {
            "Pending": "orange",
            "Settled": "green",
            "Cancelled": "red",
        }[frm.doc.status] || "gray";

        if (!frm.is_new()) {
            frm.set_intro(
                __("{0} commission of {1} — Status: {2}", [
                    frm.doc.commission_type,
                    format_currency(frm.doc.commission_amount),
                    frm.doc.status,
                ]),
                color
            );
        }
    },
});
