import frappe
from frappe.model.document import Document

DEFAULT_CHECKLIST_ITEMS = [
    ("Walls & Ceiling", "Structural"),
    ("Flooring", "Structural"),
    ("Doors & Windows", "Structural"),
    ("Electrical Points", "Electrical"),
    ("Switchboards & Wiring", "Electrical"),
    ("Plumbing Fixtures", "Plumbing"),
    ("Water Supply", "Plumbing"),
    ("Kitchen Fittings", "Fixtures"),
    ("Bathroom Fittings", "Fixtures"),
    ("Cleaning & Pest Control", "Cleanliness"),
    ("Fire Safety Equipment", "Safety"),
    ("Common Area Access", "Safety"),
]


class InspectionChecklist(Document):
    def validate(self):
        if self.status == "Completed" and not self.checklist_items:
            frappe.throw(frappe._("Add at least one checklist item before marking as Completed"))


@frappe.whitelist()
def get_default_items():
    return [
        {"item_name": name, "category": cat, "condition": ""}
        for name, cat in DEFAULT_CHECKLIST_ITEMS
    ]
