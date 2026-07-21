import frappe
from frappe.utils import getdate, today, add_months, formatdate


FREQUENCY_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Half-Yearly": 6,
    "Yearly": 12,
}


def run_daily_billing():
    """Scheduled daily job — generates rent invoices for due lease/rental allocations."""
    today_date = getdate(today())

    allocations = frappe.get_all(
        "Property Allocation",
        filters={
            "docstatus": 1,
            "status": "Active",
            "allocation_type": ["in", ["Lease", "Rental"]],
            "next_billing_date": ["<=", today_date],
            "rent_amount": [">", 0],
        },
        fields=[
            "name", "customer", "property_unit", "rent_amount",
            "billing_frequency", "next_billing_date", "end_date",
        ],
    )

    for alloc in allocations:
        if alloc.end_date and getdate(alloc.end_date) < today_date:
            _expire_allocation(alloc.name)
            continue

        try:
            invoice_name = _create_rent_invoice(alloc)
            _log_invoice(alloc, invoice_name)
            _advance_billing_date(alloc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Rent Billing Error: {alloc.name}")


def _create_rent_invoice(alloc):
    settings = frappe.get_single("Property Core Settings")

    unit = frappe.get_doc("Property Unit", alloc.property_unit)
    item_code = settings.rent_item_code or unit.item_code or unit.unit_type

    if not frappe.db.exists("Item", item_code):
        frappe.throw(
            frappe._(
                "Rent Item '{0}' not found. Set 'Rent Item Code' in Property Core Settings."
            ).format(item_code)
        )

    period_label = _period_label(alloc.next_billing_date, alloc.billing_frequency)

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = alloc.customer
    invoice.due_date = alloc.next_billing_date
    invoice.append("items", {
        "item_code": item_code,
        "description": "Rent — {} ({})".format(unit.unit_number, period_label),
        "qty": 1,
        "rate": alloc.rent_amount,
    })
    invoice.insert(ignore_permissions=True)
    return invoice.name


def _log_invoice(alloc, invoice_name):
    months = FREQUENCY_MONTHS.get(alloc.billing_frequency or "Monthly", 1)
    period_end = add_months(alloc.next_billing_date, months)

    log = frappe.new_doc("Rent Invoice Log")
    log.allocation = alloc.name
    log.period_label = _period_label(alloc.next_billing_date, alloc.billing_frequency)
    log.period_start = alloc.next_billing_date
    log.period_end = period_end
    log.invoice = invoice_name
    log.status = "Invoiced"
    log.insert(ignore_permissions=True)


def _advance_billing_date(alloc):
    months = FREQUENCY_MONTHS.get(alloc.billing_frequency or "Monthly", 1)
    new_date = add_months(alloc.next_billing_date, months)
    frappe.db.set_value(
        "Property Allocation", alloc.name, "next_billing_date", new_date, update_modified=False
    )


def _expire_allocation(allocation_name):
    frappe.db.set_value(
        "Property Allocation", allocation_name, "status", "Expired", update_modified=False
    )


def _period_label(billing_date, frequency):
    from frappe.utils import getdate as gd
    d = gd(billing_date)
    if frequency in ("Monthly", None, ""):
        return d.strftime("%b %Y")
    return "{} to {}".format(
        formatdate(billing_date, "dd MMM yyyy"),
        formatdate(
            add_months(billing_date, FREQUENCY_MONTHS.get(frequency, 1)),
            "dd MMM yyyy",
        ),
    )
