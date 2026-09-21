// Frappe's Geolocation control draws a map and gives you no way to get
// anywhere on it — on a country-sized map that means dragging from the middle
// of India to your layout every time.
//
// The search sits *on the map*, not behind a toolbar button: you look at the
// map, you type where it should be, it goes there. It takes the three things
// people actually have to hand — a place name, coordinates pasted out of
// anywhere, or the Google Maps link somebody sent on WhatsApp (the short
// maps.app.goo.gl kind included; the server follows it).

frappe.provide("property_core.geo");

property_core.geo = {
	attach(frm) {
		if (frm.is_new()) return;
		this.mount(frm);

		// The control rebuilds its DOM on every refresh of the field, which
		// throws the search bar away with it.
		setTimeout(() => this.mount(frm), 300);
	},

	field(frm) {
		return frm.get_field("geo_location");
	},

	mount(frm) {
		const field = this.field(frm);
		if (!field || !field.$wrapper || !field.$wrapper.length) return;
		if (field.$wrapper.find(".property-geo-search").length) return;

		const $bar = $(`
			<div class="property-geo-search" style="display:flex;gap:6px;margin-bottom:8px;align-items:center">
				<input type="text" class="form-control input-sm property-geo-query"
					   placeholder="${__("Search a place, paste coordinates, or a Google Maps link")}"
					   style="flex:1">
				<button class="btn btn-sm btn-default property-geo-go">${__("Find")}</button>
				<button class="btn btn-sm btn-default property-geo-open" title="${__("Open in Google Maps")}">↗</button>
			</div>
			<div class="property-geo-results" style="margin-bottom:8px"></div>
		`);

		const $anchor = field.$wrapper.find(".control-input-wrapper").first();
		($anchor.length ? $anchor : field.$wrapper).prepend($bar);

		const run = () => this.search(frm, $bar.find(".property-geo-query").val());
		$bar.find(".property-geo-go").on("click", (event) => {
			event.preventDefault();
			run();
		});
		$bar.find(".property-geo-query").on("keydown", (event) => {
			if (event.key === "Enter") {
				event.preventDefault();
				run();
			}
		});
		$bar.find(".property-geo-open").on("click", (event) => {
			event.preventDefault();
			const link =
				frm.doc.map_link ||
				(frm.doc.latitude &&
					`https://www.google.com/maps/search/?api=1&query=${frm.doc.latitude},${frm.doc.longitude}`);
			if (link) window.open(link, "_blank");
			else frappe.show_alert({ message: __("No location set yet"), indicator: "orange" });
		});
	},

	results_box(frm) {
		return this.field(frm).$wrapper.find(".property-geo-results");
	},

	search(frm, query) {
		query = (query || "").trim();
		if (!query) return;

		const $out = this.results_box(frm);
		$out.html(`<div class="text-muted small">${__("Looking...")}</div>`);

		frappe.call({
			method: "property_core.property_core.geo.resolve",
			args: { query: query },
			error: () => $out.empty(),
			callback: (r) => {
				const results = ((r.message || {}).results) || [];
				if (!results.length) {
					$out.html(`<div class="text-muted small">${__("Nothing found.")}</div>`);
					return;
				}

				// One hit and nothing to choose between — just go there.
				if (results.length === 1) {
					$out.empty();
					this.apply(frm, results[0]);
					return;
				}

				$out.html(
					results
						.map(
							(row, index) => `
						<div class="geo-result" data-index="${index}"
							 style="padding:6px 8px;border:1px solid var(--border-color);border-radius:4px;
									margin-bottom:4px;cursor:pointer">
							<div class="small">${frappe.utils.escape_html(row.label)}</div>
							<div class="text-muted small">${row.latitude}, ${row.longitude}</div>
						</div>`
						)
						.join("")
				);
				$out.find(".geo-result").on("click", (event) => {
					const index = $(event.currentTarget).data("index");
					$out.empty();
					this.apply(frm, results[index]);
				});
			},
		});
	},

	apply(frm, result) {
		frm.set_value("geo_location", result.geo_location);
		frm.set_value("latitude", result.latitude);
		frm.set_value("longitude", result.longitude);
		frm.set_value(
			"map_link",
			`https://www.google.com/maps/search/?api=1&query=${result.latitude},${result.longitude}`
		);

		frappe.show_alert({
			message: __("Location set to {0}, {1} — save to keep it", [
				result.latitude,
				result.longitude,
			]),
			indicator: "green",
		});

		// The Leaflet layer only redraws when the field refreshes; the search
		// bar goes with it, so put it back and then fly the map to the pin.
		frm.refresh_field("geo_location");
		setTimeout(() => {
			this.mount(frm);
			this.centre(frm, result);
		}, 150);
	},

	centre(frm, result) {
		const field = this.field(frm);
		const map = field && field.map;
		if (map && map.setView) {
			map.setView([result.latitude, result.longitude], 16);
			map.invalidateSize();
		}
	},
};

frappe.ui.form.on("Property", {
	refresh(frm) {
		property_core.geo.attach(frm);
	},
	geo_location(frm) {
		setTimeout(() => property_core.geo.mount(frm), 150);
	},
});

frappe.ui.form.on("Property Unit", {
	refresh(frm) {
		property_core.geo.attach(frm);
	},
	geo_location(frm) {
		setTimeout(() => property_core.geo.mount(frm), 150);
	},
});
