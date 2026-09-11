import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc

from property_core.property_core.utils.allocation_engine import (
    generate_payment_plan,
    resolve_total_price,
)
from property_core.property_core.utils.availability_engine import (
    assert_unit_available,
    release_unit,
    reserve_unit,
)
from property_core.property_core.utils.drive_folders import ensure_booking_folder
from property_core.property_core.utils.portal_user import ensure_portal_user


class PropertyBooking(Document):
    def validate(self):
        if self.is_new():
            assert_unit_available(self.property_unit)
        self.set_agreement_value()
        self.validate_booking_amount()

    def after_insert(self):
        self.provision_portal_user()

    def provision_portal_user(self):
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
        ensure_booking_folder(self)
        self.close_opportunity()
        # Again on submit, not just after_insert: when the customer was created
        # moments earlier the Contact carrying their email may not have been
        # linked yet, and a booked customer must be able to log in.
        self.provision_portal_user()
        self.start_maintenance()

    def on_cancel(self):
        self.booking_status = "Cancelled"
        release_unit(self.property_unit)

    # ------------------------------------------------------------------ #

    def set_agreement_value(self):
        if not self.total_price:
            self.total_price = resolve_total_price(self)

    def validate_booking_amount(self):
        if self.total_price and self.booking_amount and self.booking_amount > self.total_price:
            frappe.throw(
                _("Booking amount {0} is more than the agreement value {1}.").format(
                    frappe.format_value(self.booking_amount, {"fieldtype": "Currency"}),
                    frappe.format_value(self.total_price, {"fieldtype": "Currency"}),
                )
            )

    def start_maintenance(self):
        """Maintenance runs from the day the unit is taken, and anything already
        due is billed now.

        Waiting for the nightly job meant a freshly booked unit showed no
        charges at all until the next morning -- the owner could not see what
        they had signed up for on the day they signed up for it.
        """
        unit = frappe.db.get_value(
            "Property Unit", self.property_unit,
            ["maintenance_plan_template", "maintenance_start_date", "pause_maintenance"],
            as_dict=True,
        )
        if not unit or not unit.maintenance_plan_template or unit.pause_maintenance:
            return

        if not unit.maintenance_start_date:
            frappe.db.set_value(
                "Property Unit", self.property_unit,
                "maintenance_start_date", self.booking_date, update_modified=False,
            )

        try:
            from frappe.utils import getdate, today

            from property_core.property_operations.utils.maintenance_billing import _bill_unit

            _bill_unit(frappe.get_doc("Property Unit", self.property_unit), getdate(today()))
        except Exception:
            # The booking stands whether or not the first charge could be raised.
            frappe.log_error(frappe.get_traceback(), f"Maintenance on booking: {self.name}")

    def close_opportunity(self):
        """A booked unit means the opportunity is won -- otherwise it sits in
        the pipeline forever and every funnel report lies."""
        if not self.opportunity:
            return
        if frappe.db.get_value("Opportunity", self.opportunity, "status") in ("Converted", "Lost"):
            return
        frappe.db.set_value("Opportunity", self.opportunity, "status", "Converted")


def on_submit(doc, method=None):
    pass


def on_cancel(doc, method=None):
    pass


# ---------------------------------------------------------------------- #
# Create > Property Booking
# ---------------------------------------------------------------------- #


@frappe.whitelist()
def make_from_opportunity(source_name, target_doc=None):
    """The missing link in the funnel: Lead -> Opportunity -> Property Booking.

    Opportunity is where the requirement was agreed, so that is where the
    booking should start from -- the same way Create > Opportunity works on
    Lead.
    """

    def post_process(source, target):
        target.opportunity = source.name
        if source.opportunity_from == "Lead":
            target.lead = source.party_name
        target.customer = _customer_for(source)
        if target.property_unit and not target.total_price:
            target.total_price = (
                frappe.db.get_value("Property Unit", target.property_unit, "base_price") or 0
            )

    doc = get_mapped_doc(
        "Opportunity",
        source_name,
        {
            "Opportunity": {
                "doctype": "Property Booking",
                "field_map": {
                    "custom_property_unit": "property_unit",
                    "custom_property": "unit_property",
                    "name": "opportunity",
                },
                "field_no_map": ["naming_series", "status"],
            }
        },
        target_doc,
        post_process,
    )
    return doc


@frappe.whitelist()
def make_from_property_unit(source_name, target_doc=None):
    """Walk-in path: customer picks a unit off the layout, book it there."""

    def post_process(source, target):
        target.property_unit = source.name
        target.unit_property = source.property
        target.total_price = source.base_price

    return get_mapped_doc(
        "Property Unit",
        source_name,
        {
            "Property Unit": {
                "doctype": "Property Booking",
                "field_map": {"property": "unit_property", "customer": "customer"},
                "field_no_map": ["naming_series", "project"],
            }
        },
        target_doc,
        post_process,
    )


def _customer_for(opportunity):
    """Opportunity may point at a Lead or already at a Customer."""
    if opportunity.opportunity_from == "Customer":
        return opportunity.party_name
    if opportunity.get("customer"):
        return opportunity.customer
    if opportunity.opportunity_from == "Lead":
        return frappe.db.get_value("Customer", {"lead_name": opportunity.party_name}, "name")
    return None
