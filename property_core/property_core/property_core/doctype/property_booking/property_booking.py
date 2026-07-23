import frappe
from frappe.model.document import Document
from property_core.property_core.utils.availability_engine import (
    assert_unit_available,
    reserve_unit,
    release_unit,
)
from property_core.property_core.utils.allocation_engine import generate_payment_plan
from property_core.property_core.utils.portal_user import ensure_portal_user


class PropertyBooking(Document):
    def validate(self):
        if self.is_new():
            assert_unit_available(self.property_unit)

    def after_insert(self):
        try:
            ensure_portal_user(self.customer)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Portal User Provisioning: {self.name}")

    def before_submit(self):
        assert_unit_available(self.property_unit)
        self.booking_status = "Confirmed"

    def on_submit(self):
        reserve_unit(self.property_unit, self.customer)
        generate_payment_plan(self)

    def on_cancel(self):
        self.booking_status = "Cancelled"
        release_unit(self.property_unit)


def on_submit(doc, method=None):
    pass


def on_cancel(doc, method=None):
    pass
