import frappe
from frappe.model.document import Document
from property_core.property_core.utils.availability_engine import allocate_unit


class PropertyAllocation(Document):
    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(frappe._("End Date cannot be before Start Date"))

    def before_submit(self):
        self.status = "Active"

    def on_submit(self):
        allocate_unit(self.property_unit, self.customer, self.allocation_type)
        self.activate_agreement()

    def on_cancel(self):
        self.status = "Terminated"
        self.release_allocation()

    def activate_agreement(self):
        if self.agreement:
            frappe.db.set_value("Property Agreement", self.agreement, "agreement_status", "Active")

    def release_allocation(self):
        unit = frappe.get_doc("Property Unit", self.property_unit)
        unit.set_availability_status("Available")


def on_submit(doc, method=None):
    pass


def on_cancel(doc, method=None):
    pass
