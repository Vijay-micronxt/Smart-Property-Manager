import frappe
from frappe.model.document import Document


class Property(Document):
    def validate(self):
        self.validate_launch_date()

    def validate_launch_date(self):
        if self.launch_date and self.status == "Active":
            pass  # launch_date can be set freely; no constraint needed here

    def before_save(self):
        pass
