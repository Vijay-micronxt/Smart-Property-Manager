// A Project is the construction side of a development; the plots being sold
// belong to its Property. JD's old button opened a layout keyed on the Project
// and its custom_plots table -- this one opens the same development's real
// inventory, so the layout and the units people book are one set of records.

frappe.ui.form.on("Project", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Plot Layout"), () => open_layout(frm)).addClass("btn-primary");

        frm.add_custom_button(__("Property Units"), () => {
            linked_property(frm).then((property) => {
                if (!property) return offer_property(frm);
                frappe.set_route("List", "Property Unit", { property: property });
            });
        }, __("View"));
    },
});

function linked_property(frm) {
    return frappe.db
        .get_list("Property", { filters: { project: frm.doc.name }, fields: ["name"], limit: 1 })
        .then((rows) => (rows && rows.length ? rows[0].name : null));
}

function open_layout(frm) {
    linked_property(frm).then((property) => {
        if (!property) return offer_property(frm);
        frappe.route_options = { property: property };
        frappe.set_route("plot-layout-editor");
    });
}

// Without a Property there is no inventory to draw, so say that plainly and
// offer the one step that fixes it.
function offer_property(frm) {
    frappe.confirm(
        __(
            "No Property is linked to this project yet, so there are no units to lay out. Create one now?"
        ),
        () => {
            frappe.new_doc("Property", {
                project: frm.doc.name,
                property_name: frm.doc.project_name,
                company: frm.doc.company,
            });
        }
    );
}
