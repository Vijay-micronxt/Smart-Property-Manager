import frappe
from frappe.model.document import Document


class CommissionSettlement(Document):
    def before_validate(self):
        self.total_amount = sum(
            row.commission_amount or 0 for row in self.commission_entries
        )

    def validate(self):
        if not self.commission_entries:
            frappe.throw(frappe._("Add at least one Commission Entry to settle"))
        self._validate_entries()

    def _validate_entries(self):
        for row in self.commission_entries:
            entry_sp = frappe.db.get_value("Commission Entry", row.commission_entry, "sales_person")
            if entry_sp != self.sales_person:
                frappe.throw(
                    frappe._("Commission Entry {0} belongs to a different Sales Person ({1}).").format(
                        row.commission_entry, entry_sp
                    )
                )
            status = frappe.db.get_value("Commission Entry", row.commission_entry, "status")
            if status != "Pending":
                frappe.throw(
                    frappe._("Commission Entry {0} is not in Pending status (current: {1}).").format(
                        row.commission_entry, status
                    )
                )

    def on_submit(self):
        self.status = "Submitted"
        for row in self.commission_entries:
            frappe.db.set_value(
                "Commission Entry",
                row.commission_entry,
                {"status": "Settled", "settlement": self.name},
                update_modified=False,
            )

    def on_cancel(self):
        self.status = "Draft"
        for row in self.commission_entries:
            frappe.db.set_value(
                "Commission Entry",
                row.commission_entry,
                {"status": "Pending", "settlement": None},
                update_modified=False,
            )


@frappe.whitelist()
def get_pending_entries(sales_person):
    """Return Pending commission entries for a sales person, for populating the settlement child table."""
    return frappe.get_all(
        "Commission Entry",
        filters={"sales_person": sales_person, "status": "Pending"},
        fields=["name", "booking", "property_unit", "commission_amount", "commission_date"],
        order_by="commission_date asc",
    )
