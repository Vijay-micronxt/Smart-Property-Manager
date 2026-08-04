/*
 * PlotLayoutEngine — shared SVG canvas for the site layout.
 *
 * Used by the desk Layout Editor (mode: "edit") and the customer portal
 * site map (mode: "view"). Everything is drawn in "world" coordinates on
 * an SVG viewBox, so zoom is unlimited and stays crisp — no map tiles.
 *
 * Shapes per unit: Rect (x, y, w, h, rotation about center),
 * Polygon (points: [[x, y], ...]), Circle (x, y = center, w = diameter).
 *
 * No dependencies. Exposes window.PlotLayoutEngine.
 */
(function () {
    "use strict";

    var SVG_NS = "http://www.w3.org/2000/svg";

    function svgEl(tag, attrs, parent) {
        var el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            for (var k in attrs) {
                el.setAttribute(k, attrs[k]);
            }
        }
        if (parent) {
            parent.appendChild(el);
        }
        return el;
    }

    function clamp(v, lo, hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    function PlotLayoutEngine(container, opts) {
        opts = opts || {};
        this.container = typeof container === "string" ? document.querySelector(container) : container;
        this.mode = opts.mode || "view";
        this.statusColors = opts.statusColors || {};
        this.onSelect = opts.onSelect || null;
        this.onChange = opts.onChange || null;
        this.onDrawComplete = opts.onDrawComplete || null;
        this.onTextRequest = opts.onTextRequest || null;
        this.onViewChange = opts.onViewChange || null;
        this.tooltipHtml = opts.tooltipHtml || null;
        this.unitClass = opts.unitClass || null;
        this.grid = opts.grid || 0;
        this.showGrid = opts.showGrid !== false;

        this.world = { w: 3000, h: 2000, image: null };
        this.units = [];
        this.annotations = []; /* [{type:"path",points,color,width} | {type:"emoji",x,y,size,char}] */
        this.pencilColor = "#e11d48";
        this.emojiChar = "🌳"; /* 🌳 */
        this.selected = null;
        this.drawMode = null;
        this._drawState = null;
        this._drag = null;

        this._buildDom();
        this._bindEvents();
        this.svg.classList.toggle("ple-view", this.mode !== "edit");
        this.zoomToFit();
    }

    /* ---------------- DOM ---------------- */

    PlotLayoutEngine.prototype._buildDom = function () {
        this.container.classList.add("ple-container");
        this.container.innerHTML = "";

        this.svg = svgEl("svg", { class: "ple-svg" }, this.container);
        this.gWorld = svgEl("g", {}, this.svg);
        this.gImage = svgEl("g", {}, this.gWorld);
        this.gGrid = svgEl("g", {}, this.gWorld);
        this.gAnnot = svgEl("g", {}, this.gWorld);
        this.gShapes = svgEl("g", {}, this.gWorld);
        this.gDraw = svgEl("g", {}, this.gWorld);
        this.gOverlay = svgEl("g", {}, this.gWorld);

        this.tooltip = document.createElement("div");
        this.tooltip.className = "ple-tooltip";
        this.tooltip.style.display = "none";
        this.container.appendChild(this.tooltip);

        this.vb = { x: 0, y: 0, w: this.world.w, h: this.world.h };
        this._applyVB();
    };

    PlotLayoutEngine.prototype._applyVB = function () {
        this.svg.setAttribute(
            "viewBox",
            this.vb.x + " " + this.vb.y + " " + this.vb.w + " " + this.vb.h
        );
        if (this.selected && this.mode === "edit") {
            this._renderHandles();
        }
        if (this.onViewChange) this.onViewChange();
    };

    PlotLayoutEngine.prototype.getZoomPercent = function () {
        if (!this._fitW) return 100;
        return Math.round((this._fitW / this.vb.w) * 100);
    };

    /* px on screen -> world units at current zoom */
    PlotLayoutEngine.prototype._pxToWorld = function (px) {
        var rect = this.svg.getBoundingClientRect();
        return (this.vb.w / (rect.width || 1)) * px;
    };

    PlotLayoutEngine.prototype._eventToWorld = function (evt) {
        var pt = this.svg.createSVGPoint();
        pt.x = evt.clientX;
        pt.y = evt.clientY;
        var ctm = this.svg.getScreenCTM();
        if (!ctm) return { x: 0, y: 0 };
        var p = pt.matrixTransform(ctm.inverse());
        return { x: p.x, y: p.y };
    };

    PlotLayoutEngine.prototype._snap = function (v) {
        if (!this.grid || this.grid <= 0) return v;
        return Math.round(v / this.grid) * this.grid;
    };

    /* ---------------- data ---------------- */

    PlotLayoutEngine.prototype.setData = function (data) {
        var prop = data.property || {};
        this.world.w = prop.world_width || 3000;
        this.world.h = prop.world_height || 2000;
        this.world.image = prop.layout_image || null;
        this.annotations = Array.isArray(prop.annotations) ? prop.annotations : [];
        if (data.status_colors) {
            this.statusColors = data.status_colors;
        }
        this.units = (data.units || []).map(function (u) {
            /* keep any extra fields the caller sent (e.g. mine/bookable) */
            var unit = Object.assign({}, u);
            unit.shape = u.layout_shape || null;
            unit.x = u.layout_x || 0;
            unit.y = u.layout_y || 0;
            unit.w = u.layout_w || 0;
            unit.h = u.layout_h || 0;
            unit.rotation = u.layout_rotation || 0;
            unit.points = Array.isArray(u.layout_points) ? u.layout_points : null;
            return unit;
        });
        this.render();
        this.zoomToFit();
    };

    PlotLayoutEngine.prototype.getLayoutPayload = function () {
        return this.units
            .filter(function (u) {
                return u.shape;
            })
            .map(function (u) {
                return {
                    name: u.name,
                    layout_shape: u.shape,
                    layout_x: u.x,
                    layout_y: u.y,
                    layout_w: u.w,
                    layout_h: u.h,
                    layout_rotation: u.rotation || 0,
                    layout_points: u.points || null,
                };
            });
    };

    PlotLayoutEngine.prototype.getUnit = function (name) {
        return this.units.find(function (u) {
            return u.name === name;
        });
    };

    PlotLayoutEngine.prototype.setImage = function (url, naturalW, naturalH) {
        this.world.image = url;
        if (naturalW && naturalH) {
            this.world.w = naturalW;
            this.world.h = naturalH;
        }
        this.render();
        this.zoomToFit();
    };

    PlotLayoutEngine.prototype.setWorldSize = function (w, h) {
        this.world.w = w;
        this.world.h = h;
        this.render();
    };

    PlotLayoutEngine.prototype.setMode = function (mode) {
        this.mode = mode;
        this.cancelDraw();
        this.gOverlay.innerHTML = "";
        this.svg.classList.toggle("ple-view", mode !== "edit");
        this.render();
    };

    PlotLayoutEngine.prototype.getAnnotations = function () {
        return this.annotations;
    };

    PlotLayoutEngine.prototype.addAnnotation = function (a) {
        this.annotations.push(a);
        this.render();
        if (this.onChange) this.onChange();
    };

    PlotLayoutEngine.prototype.setEmoji = function (char) {
        this.emojiChar = char;
    };

    /* ---------------- view ---------------- */

    PlotLayoutEngine.prototype.zoomToFit = function () {
        var rect = this.svg.getBoundingClientRect();
        var pad = 0.05;
        var w = this.world.w * (1 + pad * 2);
        var h = this.world.h * (1 + pad * 2);
        var aspect = (rect.width || 4) / (rect.height || 3);
        if (w / h < aspect) {
            w = h * aspect;
        } else {
            h = w / aspect;
        }
        this.vb = {
            x: (this.world.w - w) / 2,
            y: (this.world.h - h) / 2,
            w: w,
            h: h,
        };
        this._fitW = w;
        this._applyVB();
    };

    PlotLayoutEngine.prototype.zoomBy = function (factor, cx, cy) {
        if (cx === undefined) {
            cx = this.vb.x + this.vb.w / 2;
            cy = this.vb.y + this.vb.h / 2;
        }
        var minW = this.world.w / 200; /* deep zoom-in */
        var maxW = this.world.w * 10;
        var newW = clamp(this.vb.w / factor, minW, maxW);
        var scale = newW / this.vb.w;
        this.vb.x = cx - (cx - this.vb.x) * scale;
        this.vb.y = cy - (cy - this.vb.y) * scale;
        this.vb.w = newW;
        this.vb.h = this.vb.h * scale;
        this._applyVB();
    };

    PlotLayoutEngine.prototype.focusUnit = function (name, zoomFactor) {
        var u = this.getUnit(name);
        if (!u || !u.shape) return;
        var b = this._unitBBox(u);
        var rect = this.svg.getBoundingClientRect();
        var aspect = (rect.width || 4) / (rect.height || 3);
        var w = b.w * (zoomFactor || 6);
        var h = w / aspect;
        if (h < b.h * 2) {
            h = b.h * 2;
            w = h * aspect;
        }
        this.vb = { x: b.cx - w / 2, y: b.cy - h / 2, w: w, h: h };
        this._applyVB();
    };

    PlotLayoutEngine.prototype._unitBBox = function (u) {
        if (u.shape === "Polygon" && u.points && u.points.length) {
            var xs = u.points.map(function (p) { return p[0]; });
            var ys = u.points.map(function (p) { return p[1]; });
            var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
            var minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
            return { x: minX, y: minY, w: maxX - minX, h: maxY - minY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2 };
        }
        if (u.shape === "Circle") {
            var r = (u.w || 0) / 2;
            return { x: u.x - r, y: u.y - r, w: r * 2, h: r * 2, cx: u.x, cy: u.y };
        }
        return { x: u.x, y: u.y, w: u.w, h: u.h, cx: u.x + u.w / 2, cy: u.y + u.h / 2 };
    };

    /* ---------------- render ---------------- */

    PlotLayoutEngine.prototype.render = function () {
        this.gImage.innerHTML = "";
        this.gGrid.innerHTML = "";
        this.gAnnot.innerHTML = "";
        this.gShapes.innerHTML = "";

        /* world frame */
        svgEl("rect", {
            x: 0, y: 0, width: this.world.w, height: this.world.h,
            class: "ple-world-frame",
            "vector-effect": "non-scaling-stroke",
        }, this.gImage);

        if (this.world.image) {
            svgEl("image", {
                href: this.world.image,
                x: 0, y: 0,
                width: this.world.w, height: this.world.h,
                preserveAspectRatio: "none",
            }, this.gImage);
        }

        if (this.showGrid && !this.world.image) {
            this._renderGrid();
        }

        this._renderAnnotations();

        for (var i = 0; i < this.units.length; i++) {
            if (this.units[i].shape) {
                this._renderUnit(this.units[i]);
            }
        }
        if (this.selected && this.mode === "edit") {
            this._renderHandles();
        }
    };

    PlotLayoutEngine.prototype._renderAnnotations = function () {
        for (var i = 0; i < this.annotations.length; i++) {
            var a = this.annotations[i];
            var el;
            if (a.type === "path" && a.points && a.points.length > 1) {
                el = svgEl("polyline", {
                    points: a.points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
                    fill: "none",
                    stroke: a.color || "#e11d48",
                    "stroke-width": a.width || this.world.w / 400,
                    "stroke-linecap": "round",
                    "stroke-linejoin": "round",
                    opacity: "0.9",
                    class: "ple-annot",
                }, this.gAnnot);
            } else if (a.type === "emoji") {
                el = svgEl("text", {
                    x: a.x, y: a.y,
                    "font-size": a.size || this.world.w / 40,
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                    class: "ple-annot ple-annot-drag",
                }, this.gAnnot);
                el.textContent = a.char || "?";
            } else if (a.type === "text") {
                el = svgEl("text", {
                    x: a.x, y: a.y,
                    "font-size": a.size || this.world.w / 55,
                    "font-weight": "700",
                    fill: a.color || "#0f172a",
                    "text-anchor": "middle",
                    "dominant-baseline": "central",
                    class: "ple-annot ple-annot-drag ple-annot-text",
                }, this.gAnnot);
                el.textContent = a.text || "";
            }
            if (el) el.dataset.idx = i;
        }
    };

    PlotLayoutEngine.prototype._eraseAt = function (pt) {
        var threshold = this._pxToWorld(10);
        for (var i = this.annotations.length - 1; i >= 0; i--) {
            var a = this.annotations[i];
            var hit = false;
            if (a.type === "emoji") {
                var half = (a.size || this.world.w / 40) / 2;
                hit = Math.abs(pt.x - a.x) < half && Math.abs(pt.y - a.y) < half;
            } else if (a.type === "text") {
                var ts = a.size || this.world.w / 55;
                var halfW = Math.max(ts, ts * (a.text || "").length * 0.3);
                hit = Math.abs(pt.x - a.x) < halfW && Math.abs(pt.y - a.y) < ts * 0.75;
            } else if (a.type === "path" && a.points) {
                var reach = threshold + (a.width || 0) / 2;
                for (var j = 0; j < a.points.length; j++) {
                    var dx = pt.x - a.points[j][0], dy = pt.y - a.points[j][1];
                    if (Math.sqrt(dx * dx + dy * dy) < reach) { hit = true; break; }
                }
            }
            if (hit) {
                this.annotations.splice(i, 1);
                this.render();
                if (this.onChange) this.onChange();
                return; /* one per event keeps erasing predictable */
            }
        }
    };

    PlotLayoutEngine.prototype._renderGrid = function () {
        var step = Math.max(50, Math.round(this.world.w / 30 / 50) * 50);
        var i;
        for (i = step; i < this.world.w; i += step) {
            svgEl("line", {
                x1: i, y1: 0, x2: i, y2: this.world.h,
                class: "ple-grid-line", "vector-effect": "non-scaling-stroke",
            }, this.gGrid);
        }
        for (i = step; i < this.world.h; i += step) {
            svgEl("line", {
                x1: 0, y1: i, x2: this.world.w, y2: i,
                class: "ple-grid-line", "vector-effect": "non-scaling-stroke",
            }, this.gGrid);
        }
    };

    PlotLayoutEngine.prototype._unitColor = function (u) {
        return this.statusColors[u.availability_status] || "#94a3b8";
    };

    PlotLayoutEngine.prototype._renderUnit = function (u) {
        var color = this._unitColor(u);
        var cls = "ple-unit";
        if (this.selected === u.name) cls += " ple-selected";
        if (this.unitClass) {
            var extra = this.unitClass(u);
            if (extra) cls += " " + extra;
        }

        var g = svgEl("g", { class: cls, "data-name": u.name }, this.gShapes);
        var b = this._unitBBox(u);
        var shape;

        if (u.shape === "Polygon" && u.points && u.points.length >= 3) {
            shape = svgEl("polygon", {
                points: u.points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
            }, g);
        } else if (u.shape === "Circle") {
            shape = svgEl("circle", { cx: u.x, cy: u.y, r: (u.w || 0) / 2 }, g);
        } else {
            shape = svgEl("rect", {
                x: u.x, y: u.y, width: u.w, height: u.h, rx: Math.min(u.w, u.h) * 0.04,
            }, g);
            if (u.rotation) {
                g.setAttribute("transform", "rotate(" + u.rotation + " " + b.cx + " " + b.cy + ")");
            }
        }
        shape.setAttribute("fill", color);
        shape.setAttribute("fill-opacity", "0.68");
        shape.setAttribute("stroke", color);
        shape.setAttribute("stroke-width", "2");
        shape.setAttribute("vector-effect", "non-scaling-stroke");
        shape.classList.add("ple-shape");

        var fontSize = clamp(Math.min(b.w, b.h) * 0.3, 6, Math.min(b.w, b.h) * 0.5);
        var label = svgEl("text", {
            x: b.cx, y: b.cy,
            class: "ple-label",
            "text-anchor": "middle",
            "dominant-baseline": "central",
            "font-size": fontSize,
        }, g);
        label.textContent = u.unit_number || u.name;
    };

    PlotLayoutEngine.prototype.select = function (name, silent) {
        this.selected = name || null;
        this.gOverlay.innerHTML = "";
        this.render();
        if (!silent && this.onSelect) {
            this.onSelect(name ? this.getUnit(name) : null);
        }
    };

    /* ---------------- edit: handles ---------------- */

    PlotLayoutEngine.prototype._renderHandles = function () {
        this.gOverlay.innerHTML = "";
        var u = this.getUnit(this.selected);
        if (!u || !u.shape) return;

        var hs = this._pxToWorld(5); /* handle half-size */
        var self = this;

        function handle(x, y, kind, index, shapeTag) {
            var el;
            if (shapeTag === "circle") {
                el = svgEl("circle", { cx: x, cy: y, r: hs, class: "ple-handle ple-handle-" + kind }, self.gOverlay);
            } else {
                el = svgEl("rect", {
                    x: x - hs, y: y - hs, width: hs * 2, height: hs * 2,
                    class: "ple-handle ple-handle-" + kind,
                }, self.gOverlay);
            }
            el.setAttribute("vector-effect", "non-scaling-stroke");
            el.dataset.kind = kind;
            if (index !== undefined) el.dataset.index = index;
            return el;
        }

        if (u.shape === "Rect") {
            var corners = this._rectCorners(u);
            ["nw", "ne", "se", "sw"].forEach(function (k, i) {
                handle(corners[i][0], corners[i][1], "resize-" + k, i);
            });
            /* rotate handle above top edge midpoint */
            var topMid = [
                (corners[0][0] + corners[1][0]) / 2,
                (corners[0][1] + corners[1][1]) / 2,
            ];
            var b = this._unitBBox(u);
            var off = this._pxToWorld(24);
            /* rotate handle sits on the line from center through topMid, extended */
            var dx = topMid[0] - b.cx, dy = topMid[1] - b.cy;
            var len = Math.sqrt(dx * dx + dy * dy) || 1;
            var px = topMid[0] + (dx / len) * off;
            var py = topMid[1] + (dy / len) * off;
            svgEl("line", {
                x1: topMid[0], y1: topMid[1], x2: px, y2: py,
                class: "ple-handle-line", "vector-effect": "non-scaling-stroke",
            }, this.gOverlay);
            handle(px, py, "rotate", undefined, "circle");
        } else if (u.shape === "Circle") {
            handle(u.x + (u.w || 0) / 2, u.y, "radius");
        } else if (u.shape === "Polygon" && u.points) {
            for (var i = 0; i < u.points.length; i++) {
                handle(u.points[i][0], u.points[i][1], "vertex", i);
            }
            /* midpoints insert new vertices */
            for (var j = 0; j < u.points.length; j++) {
                var a = u.points[j];
                var c = u.points[(j + 1) % u.points.length];
                var mp = handle((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, "midpoint", j, "circle");
                mp.classList.add("ple-handle-mid");
            }
        }
    };

    PlotLayoutEngine.prototype._rectCorners = function (u) {
        var cx = u.x + u.w / 2, cy = u.y + u.h / 2;
        var rad = ((u.rotation || 0) * Math.PI) / 180;
        var cos = Math.cos(rad), sin = Math.sin(rad);
        return [
            [-u.w / 2, -u.h / 2], [u.w / 2, -u.h / 2],
            [u.w / 2, u.h / 2], [-u.w / 2, u.h / 2],
        ].map(function (p) {
            return [cx + p[0] * cos - p[1] * sin, cy + p[0] * sin + p[1] * cos];
        });
    };

    /* ---------------- events ---------------- */

    PlotLayoutEngine.prototype._bindEvents = function () {
        var self = this;

        this.svg.addEventListener("wheel", function (evt) {
            evt.preventDefault();
            var pt = self._eventToWorld(evt);
            self.zoomBy(evt.deltaY < 0 ? 1.15 : 1 / 1.15, pt.x, pt.y);
        }, { passive: false });

        this.svg.addEventListener("pointerdown", function (evt) {
            self._onPointerDown(evt);
        });
        window.addEventListener("pointermove", function (evt) {
            self._onPointerMove(evt);
        });
        window.addEventListener("pointerup", function (evt) {
            self._onPointerUp(evt);
        });

        this.svg.addEventListener("dblclick", function (evt) {
            if (self.drawMode === "polygon" && self._drawState) {
                evt.preventDefault();
                self._finishPolygon();
            }
        });

        window.addEventListener("keydown", function (evt) {
            if (evt.key === "Escape") {
                self.cancelDraw();
                if (self.mode === "edit") self.select(null);
            }
            if (evt.key === "Enter" && self.drawMode === "polygon" && self._drawState) {
                self._finishPolygon();
            }
        });

        /* tooltip + hover */
        this.svg.addEventListener("pointermove", function (evt) {
            var g = evt.target.closest ? evt.target.closest(".ple-unit") : null;
            if (g && self.tooltipHtml && !self._drag && !self.drawMode) {
                var u = self.getUnit(g.dataset.name);
                if (u) {
                    self.tooltip.innerHTML = self.tooltipHtml(u);
                    self.tooltip.style.display = "block";
                    var crect = self.container.getBoundingClientRect();
                    var tx = evt.clientX - crect.left + 14;
                    var ty = evt.clientY - crect.top + 14;
                    var tw = self.tooltip.offsetWidth, th = self.tooltip.offsetHeight;
                    if (tx + tw > crect.width - 8) tx = tx - tw - 28;
                    if (ty + th > crect.height - 8) ty = ty - th - 28;
                    self.tooltip.style.left = tx + "px";
                    self.tooltip.style.top = ty + "px";
                }
            } else {
                self.tooltip.style.display = "none";
            }
        });
        this.svg.addEventListener("pointerleave", function () {
            self.tooltip.style.display = "none";
        });
    };

    PlotLayoutEngine.prototype._onPointerDown = function (evt) {
        if (evt.button !== 0) return;
        var pt = this._eventToWorld(evt);
        var target = evt.target;

        /* drawing */
        if (this.drawMode === "rect" || this.drawMode === "circle") {
            this._drawState = { start: pt, cur: pt };
            this._drag = { type: "draw" };
            this.svg.setPointerCapture && this.svg.setPointerCapture(evt.pointerId);
            return;
        }
        if (this.drawMode === "polygon") {
            this._drag = { type: "poly-click", start: { x: evt.clientX, y: evt.clientY } };
            return;
        }
        if (this.drawMode === "pencil") {
            this._drawState = { points: [[pt.x, pt.y]] };
            this._drag = { type: "pencil" };
            return;
        }
        if (this.drawMode === "eraser") {
            this._drag = { type: "eraser" };
            this._eraseAt(pt);
            return;
        }
        if (this.drawMode === "emoji") {
            this._drag = { type: "emoji-click", start: { x: evt.clientX, y: evt.clientY } };
            return;
        }
        if (this.drawMode === "text") {
            this._drag = { type: "text-click", start: { x: evt.clientX, y: evt.clientY } };
            return;
        }

        /* handles */
        if (this.mode === "edit" && target.classList && target.classList.contains("ple-handle")) {
            var u = this.getUnit(this.selected);
            this._drag = {
                type: "handle",
                kind: target.dataset.kind,
                index: target.dataset.index !== undefined ? parseInt(target.dataset.index, 10) : null,
                unit: u,
                start: pt,
                orig: JSON.parse(JSON.stringify({ x: u.x, y: u.y, w: u.w, h: u.h, rotation: u.rotation, points: u.points })),
            };
            if (this._drag.kind === "midpoint") {
                /* insert vertex at midpoint, then drag it as a vertex */
                var i = this._drag.index;
                var a = u.points[i], c = u.points[(i + 1) % u.points.length];
                u.points.splice(i + 1, 0, [(a[0] + c[0]) / 2, (a[1] + c[1]) / 2]);
                this._drag.kind = "vertex";
                this._drag.index = i + 1;
                this._drag.orig = JSON.parse(JSON.stringify({ x: u.x, y: u.y, w: u.w, h: u.h, rotation: u.rotation, points: u.points }));
            }
            evt.stopPropagation();
            return;
        }

        /* emoji / text sticker drag (edit mode) */
        if (this.mode === "edit" && target.classList && target.classList.contains("ple-annot-drag")) {
            var ai = parseInt(target.dataset.idx, 10);
            if (!isNaN(ai) && this.annotations[ai]) {
                this._drag = {
                    type: "annot-move", index: ai, start: pt,
                    orig: { x: this.annotations[ai].x, y: this.annotations[ai].y },
                };
                return;
            }
        }

        /* unit body */
        var g = target.closest ? target.closest(".ple-unit") : null;
        if (g) {
            var name = g.dataset.name;
            if (this.mode === "edit") {
                if (this.selected !== name) this.select(name);
                var unit = this.getUnit(name);
                this._drag = {
                    type: "move",
                    unit: unit,
                    start: pt,
                    orig: JSON.parse(JSON.stringify({ x: unit.x, y: unit.y, points: unit.points })),
                    moved: false,
                };
            } else {
                this.select(name);
            }
            return;
        }

        /* background: pan (and deselect on plain click) */
        this._drag = { type: "pan", start: { x: evt.clientX, y: evt.clientY }, vb: { x: this.vb.x, y: this.vb.y }, moved: false };
    };

    PlotLayoutEngine.prototype._onPointerMove = function (evt) {
        if (this.drawMode === "polygon" && this._drawState) {
            this._drawState.cur = this._eventToWorld(evt);
            this._renderDrawPreview();
        }
        if (!this._drag) return;
        var pt = this._eventToWorld(evt);
        var d = this._drag;

        if (d.type === "pan") {
            var scale = this.vb.w / (this.svg.getBoundingClientRect().width || 1);
            var dx = (evt.clientX - d.start.x) * scale;
            var dy = (evt.clientY - d.start.y) * scale;
            if (Math.abs(evt.clientX - d.start.x) + Math.abs(evt.clientY - d.start.y) > 3) d.moved = true;
            this.vb.x = d.vb.x - dx;
            this.vb.y = d.vb.y - dy;
            this._applyVB();
            return;
        }

        if (d.type === "draw") {
            this._drawState.cur = pt;
            this._renderDrawPreview();
            return;
        }

        if (d.type === "pencil" && this._drawState) {
            var lp = this._drawState.points[this._drawState.points.length - 1];
            var pdx = pt.x - lp[0], pdy = pt.y - lp[1];
            if (Math.sqrt(pdx * pdx + pdy * pdy) > this._pxToWorld(2)) {
                this._drawState.points.push([pt.x, pt.y]);
                this._renderPencilPreview();
            }
            return;
        }

        if (d.type === "eraser") {
            this._eraseAt(pt);
            return;
        }

        if (d.type === "annot-move") {
            var an = this.annotations[d.index];
            an.x = d.orig.x + (pt.x - d.start.x);
            an.y = d.orig.y + (pt.y - d.start.y);
            this.render();
            return;
        }

        if (this.mode !== "edit") return;

        if (d.type === "move") {
            var mdx = this._snap(pt.x - d.start.x);
            var mdy = this._snap(pt.y - d.start.y);
            if (Math.abs(mdx) + Math.abs(mdy) > 0) d.moved = true;
            var u = d.unit;
            if (u.shape === "Polygon" && d.orig.points) {
                u.points = d.orig.points.map(function (p) {
                    return [p[0] + mdx, p[1] + mdy];
                });
            } else {
                u.x = d.orig.x + mdx;
                u.y = d.orig.y + mdy;
            }
            this.render();
            return;
        }

        if (d.type === "handle") {
            this._applyHandleDrag(d, pt);
            this.render();
        }
    };

    PlotLayoutEngine.prototype._applyHandleDrag = function (d, pt) {
        var u = d.unit;

        if (d.kind === "rotate") {
            var b = this._unitBBox(u);
            var ang = (Math.atan2(pt.y - b.cy, pt.x - b.cx) * 180) / Math.PI + 90;
            u.rotation = Math.round(ang);
            if (Math.abs(((u.rotation % 90) + 90) % 90) < 4) {
                u.rotation = Math.round(u.rotation / 90) * 90; /* snap to right angles */
            }
            return;
        }

        if (d.kind === "radius") {
            u.w = Math.max(4, this._snap(Math.abs(pt.x - u.x) * 2));
            u.h = u.w;
            return;
        }

        if (d.kind === "vertex") {
            u.points[d.index] = [this._snap(pt.x), this._snap(pt.y)];
            return;
        }

        if (d.kind && d.kind.indexOf("resize-") === 0) {
            /* resize in the rect's local (rotated) frame, opposite corner fixed */
            var corner = d.kind.slice(7); /* nw ne se sw */
            var o = d.orig;
            var cx = o.x + o.w / 2, cy = o.y + o.h / 2;
            var rad = ((o.rotation || 0) * Math.PI) / 180;
            var cos = Math.cos(rad), sin = Math.sin(rad);
            /* pointer into local frame */
            var lx = (pt.x - cx) * cos + (pt.y - cy) * sin;
            var ly = -(pt.x - cx) * sin + (pt.y - cy) * cos;
            var sx = corner === "ne" || corner === "se" ? 1 : -1;
            var sy = corner === "sw" || corner === "se" ? 1 : -1;
            /* fixed corner in local frame */
            var fx = -sx * (o.w / 2), fy = -sy * (o.h / 2);
            var nw = Math.max(4, this._snap((lx - fx) * sx));
            var nh = Math.max(4, this._snap((ly - fy) * sy));
            /* new center in local frame relative to old center */
            var ncx = fx + (sx * nw) / 2, ncy = fy + (sy * nh) / 2;
            /* back to world */
            var wx = cx + ncx * cos - ncy * sin;
            var wy = cy + ncx * sin + ncy * cos;
            u.w = nw;
            u.h = nh;
            u.x = wx - nw / 2;
            u.y = wy - nh / 2;
        }
    };

    PlotLayoutEngine.prototype._onPointerUp = function (evt) {
        var d = this._drag;

        if (d && d.type === "pencil") {
            var stroke = this._drawState ? this._drawState.points : null;
            this._drawState = null;
            this.gDraw.innerHTML = "";
            this._drag = null;
            if (stroke && stroke.length > 1) {
                this.annotations.push({
                    type: "path", points: stroke,
                    color: this.pencilColor, width: this.world.w / 400,
                });
                this.render();
                if (this.onChange) this.onChange();
            }
            return; /* stay in pencil mode for the next stroke */
        }

        if (d && d.type === "eraser") {
            this._drag = null;
            return; /* stay in eraser mode */
        }

        if (d && d.type === "emoji-click") {
            var eMoved = Math.abs(evt.clientX - d.start.x) + Math.abs(evt.clientY - d.start.y) > 4;
            this._drag = null;
            if (!eMoved) {
                var ep = this._eventToWorld(evt);
                this.annotations.push({
                    type: "emoji", x: ep.x, y: ep.y,
                    size: this.world.w / 40, char: this.emojiChar,
                });
                this.render();
                if (this.onChange) this.onChange();
            }
            return; /* stay in emoji mode */
        }

        if (d && d.type === "text-click") {
            var tMoved = Math.abs(evt.clientX - d.start.x) + Math.abs(evt.clientY - d.start.y) > 4;
            this._drag = null;
            if (!tMoved && this.onTextRequest) {
                this.onTextRequest(this._eventToWorld(evt));
            }
            return; /* stay in text mode */
        }

        if (d && d.type === "annot-move") {
            this._drag = null;
            if (this.onChange) this.onChange();
            return;
        }

        if (d && d.type === "poly-click") {
            var moved = Math.abs(evt.clientX - d.start.x) + Math.abs(evt.clientY - d.start.y) > 4;
            this._drag = null;
            if (!moved) {
                var pt = this._eventToWorld(evt);
                if (!this._drawState) this._drawState = { points: [] };
                this._drawState.points.push([this._snap(pt.x), this._snap(pt.y)]);
                this._renderDrawPreview();
            }
            return;
        }

        if (d && d.type === "draw" && this._drawState) {
            var s = this._drawState.start, c = this._drawState.cur;
            var shape = null;
            if (this.drawMode === "rect") {
                var x = Math.min(s.x, c.x), y = Math.min(s.y, c.y);
                var w = Math.abs(c.x - s.x), h = Math.abs(c.y - s.y);
                if (w > 4 && h > 4) {
                    shape = { shape: "Rect", x: this._snap(x), y: this._snap(y), w: this._snap(w), h: this._snap(h), rotation: 0 };
                }
            } else if (this.drawMode === "circle") {
                var r = Math.sqrt(Math.pow(c.x - s.x, 2) + Math.pow(c.y - s.y, 2));
                if (r > 3) {
                    shape = { shape: "Circle", x: this._snap(s.x), y: this._snap(s.y), w: this._snap(r * 2), h: this._snap(r * 2), rotation: 0 };
                }
            }
            this._drawState = null;
            this.gDraw.innerHTML = "";
            if (shape) {
                this.drawMode = null;
                this.svg.classList.remove("ple-drawing");
                if (this.onDrawComplete) this.onDrawComplete(shape);
            }
            this._drag = null;
            return;
        }

        if (d && d.type === "pan" && !d.moved && this.mode === "edit" && !this.drawMode) {
            this.select(null);
        }
        if (d && (d.type === "move" || d.type === "handle")) {
            if (d.type !== "move" || d.moved) {
                if (this.onChange) this.onChange();
            }
            this._renderHandles();
        }
        this._drag = null;
    };

    /* ---------------- drawing ---------------- */

    PlotLayoutEngine.prototype.startDraw = function (kind) {
        this.cancelDraw();
        this.drawMode = kind; /* rect | polygon | circle */
        this.select(null, true);
        this.svg.classList.add("ple-drawing");
    };

    PlotLayoutEngine.prototype.cancelDraw = function () {
        this.drawMode = null;
        this._drawState = null;
        this.gDraw.innerHTML = "";
        this.svg.classList.remove("ple-drawing");
    };

    PlotLayoutEngine.prototype._renderDrawPreview = function () {
        this.gDraw.innerHTML = "";
        var st = this._drawState;
        if (!st) return;

        if (this.drawMode === "rect" && st.start && st.cur) {
            svgEl("rect", {
                x: Math.min(st.start.x, st.cur.x),
                y: Math.min(st.start.y, st.cur.y),
                width: Math.abs(st.cur.x - st.start.x),
                height: Math.abs(st.cur.y - st.start.y),
                class: "ple-draw-preview", "vector-effect": "non-scaling-stroke",
            }, this.gDraw);
        } else if (this.drawMode === "circle" && st.start && st.cur) {
            var r = Math.sqrt(Math.pow(st.cur.x - st.start.x, 2) + Math.pow(st.cur.y - st.start.y, 2));
            svgEl("circle", {
                cx: st.start.x, cy: st.start.y, r: r,
                class: "ple-draw-preview", "vector-effect": "non-scaling-stroke",
            }, this.gDraw);
        } else if (this.drawMode === "polygon" && st.points && st.points.length) {
            var pts = st.points.map(function (p) { return p[0] + "," + p[1]; }).join(" ");
            svgEl("polyline", {
                points: pts + (st.cur ? " " + st.cur.x + "," + st.cur.y : ""),
                class: "ple-draw-preview", "vector-effect": "non-scaling-stroke",
            }, this.gDraw);
            var hs = this._pxToWorld(4);
            for (var i = 0; i < st.points.length; i++) {
                svgEl("circle", {
                    cx: st.points[i][0], cy: st.points[i][1], r: hs,
                    class: "ple-handle", "vector-effect": "non-scaling-stroke",
                }, this.gDraw);
            }
        }
    };

    PlotLayoutEngine.prototype._renderPencilPreview = function () {
        this.gDraw.innerHTML = "";
        var st = this._drawState;
        if (!st || !st.points || st.points.length < 2) return;
        svgEl("polyline", {
            points: st.points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
            fill: "none",
            stroke: this.pencilColor,
            "stroke-width": this.world.w / 400,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
            opacity: "0.9",
        }, this.gDraw);
    };

    PlotLayoutEngine.prototype._finishPolygon = function () {
        var st = this._drawState;
        if (!st || !st.points || st.points.length < 3) {
            this.cancelDraw();
            return;
        }
        var shape = { shape: "Polygon", points: st.points, x: 0, y: 0, w: 0, h: 0, rotation: 0 };
        this.cancelDraw();
        if (this.onDrawComplete) this.onDrawComplete(shape);
    };

    /* apply a drawn shape (from onDrawComplete) to a unit */
    PlotLayoutEngine.prototype.assignShape = function (unitName, shape) {
        var u = this.getUnit(unitName);
        if (!u) return;
        u.shape = shape.shape;
        u.x = shape.x;
        u.y = shape.y;
        u.w = shape.w;
        u.h = shape.h;
        u.rotation = shape.rotation || 0;
        u.points = shape.points || null;
        this.render();
        this.select(unitName);
        if (this.onChange) this.onChange();
    };

    PlotLayoutEngine.prototype.removeShape = function (unitName) {
        var u = this.getUnit(unitName);
        if (!u) return;
        u.shape = null;
        u.points = null;
        this.select(null);
        if (this.onChange) this.onChange();
    };

    PlotLayoutEngine.prototype.deleteVertex = function (unitName, index) {
        var u = this.getUnit(unitName);
        if (!u || u.shape !== "Polygon" || !u.points || u.points.length <= 3) return;
        u.points.splice(index, 1);
        this.render();
        if (this.onChange) this.onChange();
    };

    window.PlotLayoutEngine = PlotLayoutEngine;
})();
