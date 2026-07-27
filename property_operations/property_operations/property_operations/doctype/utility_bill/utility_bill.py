import frappe
from frappe.model.document import Document


class UtilityBill(Document):
    def validate(self):
        self._fetch_meter_details()
        self._compute_amount()

    def _fetch_meter_details(self):
        if self.utility_meter and not self.property_unit:
            meter = frappe.get_doc("Utility Meter", self.utility_meter)
            self.property_unit = meter.property_unit
            self.customer = meter.customer
            self.rate_per_unit = meter.rate_per_unit

    def _compute_amount(self):
        if self.current_reading is not None and self.previous_reading is not None:
            if self.current_reading < self.previous_reading:
                frappe.throw(frappe._("Current Reading cannot be less than Previous Reading"))
            self.units_consumed = self.current_reading - self.previous_reading
            self.amount = self.units_consumed * (self.rate_per_unit or 0)


@frappe.whitelist()
def generate_invoice(utility_bill_name):
    """Create a Sales Invoice for this utility bill and link it back."""
    bill = frappe.get_doc("Utility Bill", utility_bill_name)

    if bill.invoice:
        frappe.throw(frappe._("Invoice already generated: {0}").format(bill.invoice))
    if bill.status == "Paid":
        frappe.throw(frappe._("This bill is already marked Paid"))

    meter = frappe.get_doc("Utility Meter", bill.utility_meter)
    item_code = meter.utility_item_code
    if not item_code:
        frappe.throw(
            frappe._("Set 'Utility Item Code' on the Utility Meter '{0}' before generating an invoice.").format(
                meter.name
            )
        )
    if not frappe.db.exists("Item", item_code):
        frappe.throw(frappe._("Item '{0}' not found in ERPNext. Please create it first.").format(item_code))

    description = "{} — {} to {} ({} {})".format(
        meter.utility_type,
        bill.billing_period_start,
        bill.billing_period_end,
        bill.units_consumed,
        meter.unit_of_measure or "units",
    )

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = bill.customer
    invoice.due_date = bill.billing_period_end
    invoice.append("items", {
        "item_code": item_code,
        "description": description,
        "qty": 1,
        "rate": bill.amount,
    })
    invoice.insert(ignore_permissions=True)

    bill.db_set("invoice", invoice.name, update_modified=True)
    bill.db_set("status", "Invoiced", update_modified=False)

    return invoice.name
