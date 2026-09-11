// Frappe's Geolocation control draws a map and gives you no way to get
// anywhere on it — on a country-sized map that means dragging from the middle
// of India to your layout every time. This adds the three ways people actually
// have a location to hand: a place name, coordinates, or a Google Maps link
// somebody sent on WhatsApp.

frappe.provide("property_core.geo");

property_core.geo = {
	attach(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Set Location"), () => this.dialog(frm), __("Map"));

		if (frm.doc.map_link) {
			frm.add_custom_button(
				__("Open in Google Maps"),
				() => window.open(frm.doc.map_link, "_blank"),
				__("Map")
			);
		}
	},

	dialog(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Find this location"),
			size: "large",
			fields: [
				{
					fieldname: "query",
					fieldtype: "Data",
					label: __("Place, coordinates, or Google Maps link"),
					reqd: 1,
					description: __(
						"e.g. Nelamangala Bengaluru &nbsp;·&nbsp; 12.9716, 77.5946 &nbsp;·&nbsp; https://maps.app.goo.gl/..."
					),
				},
				{ fieldname: "results", fieldtype: "HTML" },
			],
			primary_action_label: __("Search"),
			primary_action: (values) => this.search(d, frm, values.query),
		});

		// Enter should search, not close the dialog.
		d.fields_dict.query.$input.on("keydown", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				this.search(d, frm, d.get_value("query"));
			}
		});

		d.show();
	},

	search(d, frm, query) {
		const field = d.fields_dict.results;
		field.$wrapper.html(`<div class="text-muted">${__("Looking...")}</div>`);

		frappe.call({
			method: "property_core.property_core.geo.resolve",
			args: { query: query },
			callback: (r) => {
				const results = ((r.message || {}).results) || [];
				if (!results.length) {
					field.$wrapper.html(`<div class="text-muted">${__("Nothing found.")}</div>`);
					return;
				}

				field.$wrapper.html(
					results
						.map(
							(row, index) => `
						<div class="geo-result" data-index="${index}"
							 style="padding:8px 10px;border:1px solid var(--border-color);border-radius:4px;
									margin-bottom:6px;cursor:pointer">
							<div>${frappe.utils.escape_html(row.label)}</div>
							<div class="text-muted small">${row.latitude}, ${row.longitude}</div>
						</div>`
						)
						.join("")
				);

				field.$wrapper.find(".geo-result").on("click", function () {
					property_core.geo.apply(d, frm, results[$(this).data("index")]);
				});

				// One hit and nothing to choose between — just take it.
				if (results.length === 1) {
					property_core.geo.apply(d, frm, results[0]);
				}
			},
		});
	},

	apply(d, frm, result) {
		frm.set_value("geo_location", result.geo_location);
		frm.set_value("latitude", result.latitude);
		frm.set_value("longitude", result.longitude);
		frm.set_value("map_link",
			`https://www.google.com/maps/search/?api=1&query=${result.latitude},${result.longitude}`);

		d.hide();
		frappe.show_alert({
			message: __("Location set to {0}, {1} — save to keep it", [
				result.latitude,
				result.longitude,
			]),
			indicator: "green",
		});

		// The Leaflet control only redraws its layer when the form refreshes.
		frm.refresh_field("geo_location");
	},
};

frappe.ui.form.on("Property", {
	refresh(frm) {
		property_core.geo.attach(frm);
	},
});

frappe.ui.form.on("Property Unit", {
	refresh(frm) {
		property_core.geo.attach(frm);
	},
});
