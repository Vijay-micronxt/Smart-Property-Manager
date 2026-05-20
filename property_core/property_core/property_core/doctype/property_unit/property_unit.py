import frappe
from frappe.model.document import Document


class PropertyUnit(Document):
    def validate(self):
        self.validate_unit_number_unique()

    def validate_unit_number_unique(self):
        existing = frappe.db.exists(
            "Property Unit",
            {"property": self.property, "unit_number": self.unit_number, "name": ("!=", self.name)},
        )
        if existing:
            frappe.throw(
                frappe._("Unit Number {0} already exists for Property {1}").format(
                    self.unit_number, self.property
                )
            )

    def set_availability_status(self, status):
        self.db_set("availability_status", status, update_modified=False)
        if status in ("Allocated", "Leased"):
            pass
        elif status == "Available":
            self.db_set("customer", None, update_modified=False)
