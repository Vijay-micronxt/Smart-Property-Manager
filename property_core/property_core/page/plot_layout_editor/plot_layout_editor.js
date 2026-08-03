frappe.pages["plot-layout-editor"].on_page_load = function (wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Plot Layout Editor"),
        single_column: true,
    });

    frappe.require(
        [
            "/assets/property_core/js/plot_layout_engine.js",
            "/assets/property_core/css/plot_layout.css",
        ],
        function () {
            wrapper.plot_layout_editor = new PlotLayoutEditorPage(page, wrapper);
        }
    );
};

frappe.pages["plot-layout-editor"].on_page_show = function (wrapper) {
    var editor = wrapper.plot_layout_editor;
    var route_property = frappe.utils.get_url_arg("property") || frappe.route_options?.property;
    if (editor && route_property && route_property !== editor.property) {
        editor.load_property(route_property);
    }
    frappe.route_options = null;
};

class PlotLayoutEditorPage {
    constructor(page, wrapper) {
        this.page = page;
        this.wrapper = wrapper;
        this.property = null;
        this.dirty = false;
        this.locked = true; // view-only until the user clicks Edit Layout
        this.pending_unit = null; // sidebar unit armed for the next drawn shape

        this.make_layout();
        this.make_engine();
        this.make_page_actions();

        var route_property =
            frappe.utils.get_url_arg("property") ||
            frappe.route_options?.property ||
            localStorage.getItem("pled_last_property");
        frappe.route_options = null;
        if (route_property) {
            this.property_field.set_value(route_property);
        }

        window.addEventListener("beforeunload", (e) => {
            if (this.dirty) {
                e.preventDefault();
                e.returnValue = "";
            }
        });
    }

    make_layout() {
        this.$body = $(this.page.body);
        this.$body.html(`
            <div class="pled-wrap">
                <div class="pled-main">
                    <div class="pled-canvas-wrap">
                        <div class="pled-canvas"></div>
                        <div class="pled-rail">
                            <button class="pled-rb pled-zoom-chip" data-act="fit" title="${__("Zoom to fit")}">100%</button>
                            <button class="pled-rb pled-rb-txt" data-act="zoom-in" title="${__("Zoom in")}">&#65291;</button>
                            <button class="pled-rb pled-rb-txt" data-act="zoom-out" title="${__("Zoom out")}">&#65293;</button>
                            <div class="pled-rail-div pled-edit-only"></div>
                            <button class="pled-rb pled-edit-only active" data-tool="select" title="${__("Select / Pan")}">
                                <svg viewBox="0 0 24 24"><path d="M6 3l14 9-6.6 1.2 3.4 6.4-2.8 1.4-3.4-6.4L6 19V3z" fill="currentColor"/></svg>
                            </button>
                            <button class="pled-rb pled-edit-only" data-tool="rect" title="${__("Rectangle plot")}">
                                <svg viewBox="0 0 24 24"><rect x="4" y="6" width="16" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
                            </button>
                            <button class="pled-rb pled-edit-only" data-tool="polygon" title="${__("Polygon plot — click points, Enter/double-click to finish")}">
                                <svg viewBox="0 0 24 24"><path d="M12 3l9 6.5-3.4 10.5H6.4L3 9.5 12 3z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
                            </button>
                            <button class="pled-rb pled-edit-only" data-tool="circle" title="${__("Circle plot")}">
                                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>
                            </button>
                            <button class="pled-rb pled-rb-txt pled-edit-only" data-tool="text" title="${__("Text label")}">T</button>
                            <button class="pled-rb pled-rb-emoji pled-edit-only" data-tool="emoji" title="${__("Emoji markers")}">&#128578;</button>
                            <button class="pled-rb pled-edit-only" data-tool="pencil" title="${__("Freehand pencil")}">
                                <svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z" fill="currentColor"/></svg>
                            </button>
                            <button class="pled-rb pled-edit-only" data-tool="eraser" title="${__("Eraser — click or drag over drawings")}">
                                <svg viewBox="0 0 24 24"><path d="M15.14 3.86l5 5a2 2 0 010 2.83L13.5 18.3H8.5l-5.34-5.34a2 2 0 010-2.83l9.15-6.27a2 2 0 012.83 0z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><line x1="5" y1="21" x2="19" y2="21" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
                            </button>
                            <div class="pled-rail-div pled-edit-only"></div>
                            <button class="pled-rb pled-edit-only active" data-act="snap" title="${__("Snap to grid")}">
                                <svg viewBox="0 0 24 24"><path d="M9 3v18M15 3v18M3 9h18M3 15h18" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>
                            </button>
                            <button class="pled-rb pled-edit-only" data-act="image" title="${__("Blueprint image")}">
                                <svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="10" r="1.6" fill="currentColor"/><path d="M5 18l5-5 3 3 3-4 3 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
                            </button>
                        </div>
                        <div class="pled-pop pled-colors" style="display:none"></div>
                        <div class="pled-pop pled-emoji-palette" style="display:none"></div>
                    </div>
                    <div class="pled-side">
                        <div class="pled-side-detail"></div>
                        <div class="pled-side-search">
                            <input type="text" class="form-control input-sm" placeholder="${__("Search units...")}">
                        </div>
                        <div class="pled-side-units"></div>
                    </div>
                </div>
                <div class="pled-legend"></div>
            </div>
        `);

        this.$canvas = this.$body.find(".pled-canvas");
        this.$units = this.$body.find(".pled-side-units");
        this.$detail = this.$body.find(".pled-side-detail");
        this.$legend = this.$body.find(".pled-legend");
        this.$rail = this.$body.find(".pled-rail");
        this.$zoom_chip = this.$rail.find(".pled-zoom-chip");

        this.$rail.find("[data-tool]").on("click", (e) => {
            var tool = $(e.currentTarget).data("tool");
            this.set_tool(tool);
        });

        this.$rail.find("[data-act]").on("click", (e) => {
            var act = $(e.currentTarget).data("act");
            if (act === "fit") this.engine.zoomToFit();
            else if (act === "zoom-in") this.engine.zoomBy(1.3);
            else if (act === "zoom-out") this.engine.zoomBy(1 / 1.3);
            else if (act === "image") this.upload_image();
            else if (act === "snap") {
                var $btn = $(e.currentTarget).toggleClass("active");
                this.engine.grid = $btn.hasClass("active") ? 10 : 0;
            }
        });

        // pencil color swatches
        this.PENCIL_COLORS = ["#e11d48", "#1d4ed8", "#059669", "#f59e0b", "#7c3aed", "#0f172a", "#ffffff"];
        this.$colors = this.$body.find(".pled-colors");
        this.$colors.html(this.PENCIL_COLORS.map((c) =>
            `<button class="pled-swatch" data-color="${c}" style="background:${c}"></button>`).join(""));
        this.$colors.find(".pled-swatch").on("click", (e) => {
            var color = $(e.currentTarget).data("color");
            this.engine.pencilColor = color;
            this.$colors.find(".pled-swatch").removeClass("active");
            $(e.currentTarget).addClass("active");
        });
        this.$colors.find(".pled-swatch").first().addClass("active");

        // emoji palette
        this.EMOJIS = ["🌳", "🌴", "🌵", "🌊", "⛲", "🏠", "🏢", "🛕", "⛪", "🕌", "🚗", "🅿️", "🚧", "⚡", "💧", "🛝", "🏊", "🎾", "⚽", "🚻", "📌", "⭐"];
        this.$emojis = this.$body.find(".pled-emoji-palette");
        this.$emojis.html(this.EMOJIS.map((c) =>
            `<button class="pled-emoji" data-char="${c}">${c}</button>`).join(""));
        this.$emojis.find(".pled-emoji").on("click", (e) => {
            var char = $(e.currentTarget).data("char");
            this.engine.setEmoji(String(char));
            this.$emojis.find(".pled-emoji").removeClass("active");
            $(e.currentTarget).addClass("active");
            this.engine.startDraw("emoji");
        });
        this.$emojis.find(".pled-emoji").first().addClass("active");
        this.$body.find(".pled-side-search input").on("input", (e) => {
            this.render_units_list(e.target.value);
        });

        $(document).on("keydown.pled", (e) => {
            if (["Delete", "Backspace"].includes(e.key) && this.engine && this.engine.selected && !this.locked) {
                if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
                this.remove_selected_shape();
            }
        });
    }

    make_engine() {
        this.engine = new PlotLayoutEngine(this.$canvas[0], {
            mode: "view",
            grid: 10,
            onSelect: (unit) => this.render_detail(unit),
            onChange: () => this.set_dirty(true),
            onDrawComplete: (shape) => this.on_shape_drawn(shape),
            tooltipHtml: (u) => this.tooltip_html(u),
            onViewChange: () => {
                if (this.engine) this.$zoom_chip.text(this.engine.getZoomPercent() + "%");
            },
            onTextRequest: (pt) => {
                frappe.prompt(
                    { fieldname: "label", fieldtype: "Data", label: __("Text"), reqd: 1 },
                    (values) => {
                        this.engine.addAnnotation({
                            type: "text",
                            x: pt.x, y: pt.y,
                            size: this.engine.world.w / 50,
                            text: values.label,
                            color: this.engine.pencilColor,
                        });
                    },
                    __("Add Text Label")
                );
            },
        });
    }

    make_page_actions() {
        this.property_field = this.page.add_field({
            fieldname: "property",
            fieldtype: "Link",
            label: __("Property"),
            options: "Property",
            change: () => {
                var value = this.property_field.get_value();
                if (value && value !== this.property) {
                    this.confirm_discard(() => this.load_property(value));
                }
            },
        });

        this.update_lock_ui();
        this.page.add_menu_item(__("Reload"), () => {
            this.confirm_discard(() => this.load_property(this.property));
        });
        this.page.add_menu_item(__("Open Property"), () => {
            if (this.property) frappe.set_route("Form", "Property", this.property);
        });
    }

    confirm_discard(action) {
        if (!this.dirty) return action();
        frappe.confirm(__("You have unsaved layout changes. Discard them?"), () => {
            this.set_dirty(false);
            action();
        });
    }

    set_tool(tool) {
        if (this.locked) return;
        this.$rail.find("[data-tool]").removeClass("active");
        this.$rail.find(`[data-tool="${tool}"]`).addClass("active");
        this.$colors.toggle(tool === "pencil" || tool === "text");
        this.$emojis.toggle(tool === "emoji");
        if (tool === "select") {
            this.engine.cancelDraw();
        } else {
            this.engine.startDraw(tool);
        }
    }

    unlock_editor() {
        if (this.data && !this.data.can_write) {
            frappe.msgprint(__("You do not have write permission on this Property"));
            return;
        }
        this.locked = false;
        this.update_lock_ui();
    }

    lock_editor() {
        this.confirm_discard(() => {
            this.locked = true;
            this.update_lock_ui();
            if (this.property) this.load_property(this.property);
        });
    }

    update_lock_ui() {
        var editing = !this.locked;
        this.$body.find(".pled-edit-only").toggle(editing);
        if (!editing) {
            this.$colors.hide();
            this.$emojis.hide();
        }
        this.engine.setMode(editing ? "edit" : "view");
        if (editing) {
            this.page.set_primary_action(__("Save Layout"), () => this.save(), "small-file");
            this.page.set_secondary_action(__("Done"), () => this.lock_editor());
            this.set_tool("select");
        } else {
            this.page.set_primary_action(__("Edit Layout"), () => this.unlock_editor(), "edit");
            this.page.clear_secondary_action();
        }
        this.render_units_list(this.$body.find(".pled-side-search input").val());
    }

    load_property(property) {
        this.property = property;
        this.pending_unit = null;
        this.locked = true;
        if (this.property_field.get_value() !== property) {
            this.property_field.set_value(property);
        }
        // keep the property in the URL so a browser refresh restores it
        window.history.replaceState(null, "", "/app/plot-layout-editor?property=" + encodeURIComponent(property));
        localStorage.setItem("pled_last_property", property);
        frappe.call({
            method: "property_core.property_core.api.layout.get_layout",
            args: { property: property },
            callback: (r) => {
                if (!r.message) return;
                this.data = r.message;
                this.engine.setData(this.data);
                this.set_dirty(false);
                this.update_lock_ui();
                this.render_detail(null);
                this.render_legend();
                if (!this.data.can_write) {
                    frappe.show_alert({ message: __("Read-only: no write permission on this Property"), indicator: "orange" });
                }
            },
        });
    }

    set_dirty(dirty) {
        this.dirty = dirty;
        this.page.set_indicator(
            dirty ? __("Not Saved") : __("Saved"),
            dirty ? "orange" : "green"
        );
    }

    save() {
        if (!this.property) return;
        frappe.call({
            method: "property_core.property_core.api.layout.save_layout",
            args: {
                property: this.property,
                units: this.engine.getLayoutPayload(),
                world: {
                    width: this.engine.world.w,
                    height: this.engine.world.h,
                    layout_image: this.engine.world.image,
                },
                annotations: this.engine.getAnnotations(),
            },
            freeze: true,
            freeze_message: __("Saving layout..."),
            callback: (r) => {
                if (r.message && r.message.ok) {
                    this.set_dirty(false);
                    frappe.show_alert({ message: __("Layout saved ({0} units)", [r.message.saved]), indicator: "green" });
                }
            },
        });
    }

    upload_image() {
        if (!this.property) {
            frappe.msgprint(__("Select a Property first"));
            return;
        }
        new frappe.ui.FileUploader({
            doctype: "Property",
            docname: this.property,
            restrictions: { allowed_file_types: ["image/*"] },
            on_success: (file) => {
                var url = file.file_url;
                var img = new Image();
                img.onload = () => {
                    var has_shapes = this.engine.units.some((u) => u.shape);
                    if (!has_shapes) {
                        // no shapes yet — adopt the image's pixel size as world size
                        this.engine.setImage(url, img.naturalWidth, img.naturalHeight);
                    } else {
                        this.engine.setImage(url);
                    }
                    this.set_dirty(true);
                };
                img.src = url;
            },
        });
    }

    on_shape_drawn(shape) {
        this.set_tool("select");
        if (this.pending_unit) {
            this.engine.assignShape(this.pending_unit, shape);
            this.pending_unit = null;
            this.render_units_list();
            return;
        }
        var unplaced = this.engine.units.filter((u) => !u.shape);
        var d = new frappe.ui.Dialog({
            title: __("Assign shape to unit"),
            fields: [
                {
                    fieldname: "unit",
                    fieldtype: "Select",
                    label: __("Property Unit"),
                    reqd: 1,
                    options: unplaced.map((u) => ({ value: u.name, label: `${u.unit_number} (${u.name})` })),
                },
            ],
            primary_action_label: __("Assign"),
            primary_action: (values) => {
                d.hide();
                this.engine.assignShape(values.unit, shape);
                this.render_units_list();
            },
        });
        if (!unplaced.length) {
            frappe.msgprint(__("All units already placed. Create a new Property Unit first, or select a placed unit and delete its shape."));
            return;
        }
        d.show();
    }

    remove_selected_shape() {
        var name = this.engine.selected;
        if (!name) return;
        this.engine.removeShape(name);
        this.render_units_list();
    }

    /* ---------- sidebar ---------- */

    render_units_list(filter) {
        if (!this.engine) return;
        filter = (filter || "").toLowerCase();
        var units = this.engine.units.filter(
            (u) => !filter || (u.unit_number || "").toLowerCase().includes(filter) || u.name.toLowerCase().includes(filter)
        );
        var unplaced = units.filter((u) => !u.shape);
        var placed = units.filter((u) => u.shape);
        var colors = this.data ? this.data.status_colors : {};

        var row = (u, placed_flag) => `
            <div class="pled-unit-row ${this.pending_unit === u.name ? "pled-armed" : ""}" data-name="${u.name}" data-placed="${placed_flag}">
                <span class="pled-dot" style="background:${colors[u.availability_status] || "#94a3b8"}"></span>
                <span class="pled-unit-no">${frappe.utils.escape_html(u.unit_number || u.name)}</span>
                <span class="pled-unit-status">${frappe.utils.escape_html(u.availability_status || "")}</span>
                ${placed_flag || this.locked ? "" : `<button class="btn btn-xs btn-default pled-place">${__("Place")}</button>`}
            </div>`;

        this.$units.html(`
            ${unplaced.length ? `<div class="pled-group-title">${__("Unplaced")} (${unplaced.length})</div>` : ""}
            ${unplaced.map((u) => row(u, 0)).join("")}
            <div class="pled-group-title">${__("Placed")} (${placed.length})</div>
            ${placed.map((u) => row(u, 1)).join("")}
        `);

        this.$units.find(".pled-unit-row").on("click", (e) => {
            var name = $(e.currentTarget).data("name");
            var is_placed = $(e.currentTarget).data("placed");
            if (is_placed) {
                this.engine.select(name);
                this.engine.focusUnit(name);
            }
        });
        this.$units.find(".pled-place").on("click", (e) => {
            e.stopPropagation();
            var name = $(e.currentTarget).closest(".pled-unit-row").data("name");
            this.pending_unit = name;
            this.render_units_list(filter);
            frappe.show_alert({
                message: __("Draw a shape for {0} — pick a tool and draw", [name]),
                indicator: "blue",
            });
            this.set_tool("rect");
        });
    }

    render_detail(unit) {
        if (!unit) {
            this.$detail.html(`<div class="pled-detail-empty">${__("Click a plot on the canvas, or place an unplaced unit.")}</div>`);
            return;
        }
        var colors = this.data ? this.data.status_colors : {};
        this.$detail.html(`
            <div class="pled-detail">
                <div class="pled-detail-title">${frappe.utils.escape_html(unit.unit_number || unit.name)}</div>
                <div class="pled-detail-row">
                    <span class="pled-dot" style="background:${colors[unit.availability_status] || "#94a3b8"}"></span>
                    ${frappe.utils.escape_html(unit.availability_status || "")}
                </div>
                ${unit.area ? `<div class="pled-detail-row">${__("Area")}: ${unit.area} sq ft</div>` : ""}
                ${unit.base_price ? `<div class="pled-detail-row">${__("Price")}: ${format_currency(unit.base_price)}</div>` : ""}
                ${unit.customer_name ? `<div class="pled-detail-row">${__("Customer")}: ${frappe.utils.escape_html(unit.customer_name)}</div>` : ""}
                <div class="pled-detail-actions">
                    <button class="btn btn-xs btn-default pled-open-unit">${__("Open")}</button>
                    ${this.locked ? "" : `<button class="btn btn-xs btn-danger pled-del-shape">${__("Remove Shape")}</button>`}
                </div>
            </div>
        `);
        this.$detail.find(".pled-open-unit").on("click", () => frappe.set_route("Form", "Property Unit", unit.name));
        this.$detail.find(".pled-del-shape").on("click", () => this.remove_selected_shape());
    }

    render_legend() {
        var colors = this.data ? this.data.status_colors : {};
        this.$legend.html(
            Object.keys(colors)
                .map(
                    (s) => `<span class="pled-legend-item"><span class="pled-dot" style="background:${colors[s]}"></span>${frappe.utils.escape_html(s)}</span>`
                )
                .join("")
        );
    }

    tooltip_html(u) {
        var color = (this.data && this.data.status_colors[u.availability_status]) || "#94a3b8";
        return `
            <div class="ple-tt-title">${frappe.utils.escape_html(u.unit_number || u.name)}</div>
            <span class="ple-tt-status" style="background:${color}33;color:${color}">${frappe.utils.escape_html(u.availability_status || "")}</span>
            ${u.area ? `<div>${__("Area")}: ${u.area} sq ft</div>` : ""}
            ${u.base_price ? `<div>${__("Price")}: ${format_currency(u.base_price)}</div>` : ""}
        `;
    }
}
