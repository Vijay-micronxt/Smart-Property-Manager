import frappe
from frappe.model.document import Document
from frappe.utils import getdate, add_months
from property_core.property_core.utils.availability_engine import allocate_unit

RECURRING_TYPES = ("Lease", "Rental")
FREQUENCY_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Half-Yearly": 6,
    "Yearly": 12,
}


class PropertyAllocation(Document):
    def validate(self):
        self.validate_dates()
        self.validate_rent_fields()

    def validate_dates(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(frappe._("End Date cannot be before Start Date"))

    def validate_rent_fields(self):
        if self.allocation_type in RECURRING_TYPES:
            if self.rent_amount and self.rent_amount <= 0:
                frappe.throw(frappe._("Rent Amount must be greater than zero"))
            if self.billing_day and not (1 <= self.billing_day <= 28):
                frappe.throw(frappe._("Billing Day must be between 1 and 28"))

    def before_submit(self):
        self.status = "Active"
        if self.allocation_type in RECURRING_TYPES and self.rent_amount:
            self.next_billing_date = self._compute_first_billing_date()

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

    def _compute_first_billing_date(self):
        import datetime
        start = getdate(self.start_date)
        day = self.billing_day or 1
        try:
            return start.replace(day=day)
        except ValueError:
            # e.g. billing_day=31 in a short month — fall back to last day
            import calendar
            last_day = calendar.monthrange(start.year, start.month)[1]
            return start.replace(day=last_day)

    def advance_billing_date(self):
        months = FREQUENCY_MONTHS.get(self.billing_frequency or "Monthly", 1)
        new_date = add_months(self.next_billing_date, months)
        self.db_set("next_billing_date", new_date, update_modified=False)


def on_submit(doc, method=None):
    pass


def on_cancel(doc, method=None):
    pass


@frappe.whitelist()
def renew_lease(allocation_name, new_end_date, escalation_percent=0):
    """Extend lease end date and optionally escalate rent. Returns updated values."""
    doc = frappe.get_doc("Property Allocation", allocation_name)

    if doc.docstatus != 1 or doc.status != "Active":
        frappe.throw(frappe._("Only active submitted allocations can be renewed."))
    if doc.allocation_type not in ("Lease", "Rental"):
        frappe.throw(frappe._("Only Lease or Rental allocations support renewal."))

    escalation_percent = float(escalation_percent or 0)
    new_rent = doc.rent_amount * (1 + escalation_percent / 100)

    doc.db_set("end_date", new_end_date, update_modified=True)
    if escalation_percent:
        doc.db_set("rent_amount", new_rent, update_modified=False)

    return {
        "new_end_date": new_end_date,
        "new_rent_amount": new_rent,
        "escalation_applied": bool(escalation_percent),
    }
