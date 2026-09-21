// Opportunity is the hand-off point in the real-estate funnel: the requirement
// is agreed here, so this is where "Create > Property Booking" belongs. ERPNext
// gives Lead a Create > Opportunity button out of the box; this closes the
// other half of the chain.

frappe.ui.form.on("Opportunity", {
	setup(frm) {
		// Pick a property first and only its own free units are offered; pick a
		// unit first and any free unit in the company is fair game -- the
		// property then fills itself in below.
		frm.set_query("custom_property_unit", () => ({
			filters: frm.doc.custom_property
				? {
						property: frm.doc.custom_property,
						availability_status: ["in", ["Available", "Reserved"]],
				  }
				: { availability_status: ["in", ["Available", "Reserved"]] },
		}));

		frm.set_query("custom_property", () => ({
			filters: { status: ["!=", "Inactive"] },
		}));
	},

	refresh(frm) {
		property_core.follow_up.render(frm, "custom_follow_up_history");

		if (frm.is_new() || frm.doc.status === "Lost") return;

		frm.add_custom_button(
			__("Property Booking"),
			() =>
				frappe.model.open_mapped_doc({
					method:
						"property_core.property_core.doctype.property_booking.property_booking.make_from_opportunity",
					frm: frm,
				}),
			__("Create")
		);

		// A booking needs a Customer. Offer it from here too, so the chain does
		// not stall at the one step that has no button.
		if (frm.doc.opportunity_from === "Lead" && frm.doc.party_name) {
			frm.add_custom_button(
				__("Customer"),
				() => property_core.follow_up.create_customer(frm.doc.party_name),
				__("Create")
			);
		}

		if (frm.doc.contact_mobile || frm.doc.contact_no) {
			const number = frm.doc.contact_mobile || frm.doc.contact_no;
			frm.add_custom_button(
				__("WhatsApp"),
				() =>
					property_core.follow_up.whatsapp_dialog(
						"Opportunity",
						frm.doc.name,
						number,
						frm.doc.party_name
					),
				__("Contact")
			);
			frm.add_custom_button(
				__("Call"),
				() => property_core.follow_up.call("Opportunity", frm.doc.name, number),
				__("Contact")
			);
		}

		show_existing_bookings(frm);
	},

	custom_property(frm) {
		// A unit from the old property cannot survive the switch.
		if (frm.doc.custom_property_unit) {
			frappe.db
				.get_value("Property Unit", frm.doc.custom_property_unit, "property")
				.then((r) => {
					if (r.message && r.message.property !== frm.doc.custom_property) {
						frm.set_value("custom_property_unit", null);
					}
				});
		}
	},

	custom_property_unit(frm) {
		// The unit knows its own development -- do not make the user tell the
		// form something it can look up, and never leave the mandatory
		// Property field empty just because the unit was chosen first.
		if (!frm.doc.custom_property_unit) return;

		frappe.call({
			method: "property_core.property_core.crm.opportunity_events.resolve_unit",
			args: { property_unit: frm.doc.custom_property_unit },
			callback: ({ message }) => {
				if (!message || !message.property) return;
				if (frm.doc.custom_property !== message.property) {
					frm.set_value("custom_property", message.property);
				}
				if (message.availability_status === "Booked") {
					frm.dashboard.set_headline_alert(
						__("Unit {0} is already booked.", [message.unit_number || message.name]),
						"orange"
					);
				}
			},
		});
	},
});

function show_existing_bookings(frm) {
	frappe.db
		.get_list("Property Booking", {
			filters: { opportunity: frm.doc.name, docstatus: ["<", 2] },
			fields: ["name", "booking_status", "property_unit"],
		})
		.then((rows) => {
			if (!rows || !rows.length) return;
			const list = rows
				.map(
					(b) =>
						`<a href="/app/property-booking/${encodeURIComponent(b.name)}">${b.name}</a> — ${
							b.property_unit
						} (${b.booking_status})`
				)
				.join("<br>");
			frm.dashboard.add_comment(`${__("Booked:")}<br>${list}`, "green", true);
		});
}
