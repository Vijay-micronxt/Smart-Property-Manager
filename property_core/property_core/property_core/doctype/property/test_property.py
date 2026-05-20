import frappe
from frappe.tests.utils import FrappeTestCase


class TestProperty(FrappeTestCase):
    def test_property_creation(self):
        prop = frappe.get_doc({
            "doctype": "Property",
            "property_name": "_Test Property",
            "property_type": "Apartment",
            "company": frappe.defaults.get_user_default("company"),
            "status": "Active",
        })
        prop.insert(ignore_permissions=True)
        self.assertEqual(prop.status, "Active")
        prop.delete()
