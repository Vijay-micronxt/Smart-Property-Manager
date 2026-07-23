import frappe
from frappe.utils import getdate, today, add_months


def run_daily_maintenance_billing():
    """Scheduled daily job -- auto-generates + submits a recurring maintenance
    Sales Invoice for each Property Unit carrying a Maintenance Plan Template,
    mirroring JD's proven Plot Maintenance - Generate Invoices & Remind
    pattern (minus the WhatsApp half -- notifications are wired separately
    via Server Script, not app code).
    """
    today_date = getdate(today())

    units = frappe.get_all(
        "Property Unit",
        filters={
            "pause_maintenance": 0,
            "maintenance_plan_template": ["is", "set"],
            "maintenance_start_date": ["is", "set"],
        },
        fields=["name", "customer", "maintenance_plan_template", "maintenance_start_date"],
    )

    for unit in units:
        try:
            _bill_unit(unit, today_date)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Maintenance Billing Error: {unit.name}")

    frappe.db.commit()


def _bill_unit(unit, today_date):
    if not unit.customer:
        return

    tpl = frappe.get_cached_doc("Maintenance Plan Template", unit.maintenance_plan_template)
    if tpl.disabled:
        return

    start = getdate(unit.maintenance_start_date)
    if start > today_date:
        return

    settings = frappe.get_single("Property Core Settings")
    item_code = settings.maintenance_item_code
    if not item_code:
        frappe.throw(frappe._("Set 'Maintenance Item Code' in Property Core Settings before billing can run"))

    rows_by_month = {}
    max_month = 0
    for row in tpl.schedule:
        if row.fixed_due_date:
            due = getdate(row.fixed_due_date)
            if due <= today_date:
                _create_invoice_if_new(
                    unit, row.item_code or item_code, row.amount, due, str(due),
                    row.description or f"Maintenance charge - {unit.name} - {due}",
                )
        elif row.month_no:
            rows_by_month[row.month_no] = row
            max_month = max(max_month, row.month_no)

    repeat_n = tpl.repeat_every_n_months or 0
    repeat_amt = tpl.repeat_amount or 0
    repeat_item = tpl.repeat_item_code or item_code
    months_elapsed = (today_date.year - start.year) * 12 + (today_date.month - start.month) + 1

    month = 1
    while month <= months_elapsed:
        row = rows_by_month.get(month)
        amount = row.amount if row else None
        row_item = row.item_code or item_code if row else item_code
        row_desc = row.description if row else None

        if not amount and repeat_n and repeat_amt and month > max_month:
            if (month - max_month) % repeat_n == 0:
                amount = repeat_amt
                row_item = repeat_item
                row_desc = tpl.repeat_description

        if amount:
            due = getdate(add_months(start, month - 1))
            if due <= today_date:
                period = "{}-{:02d}".format(due.year, due.month)
                _create_invoice_if_new(
                    unit, row_item, amount, due, period,
                    row_desc or f"Maintenance charge - {unit.name} - {period}",
                )
        month += 1


def _create_invoice_if_new(unit, item_code, amount, due, period, description):
    existing = frappe.db.exists(
        "Sales Invoice",
        {"property_unit": unit.name, "maintenance_period": period, "docstatus": ["<", 2]},
    )
    if existing:
        return

    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = unit.customer
    invoice.set_posting_time = 1
    invoice.posting_date = due
    invoice.due_date = due
    invoice.property_unit = unit.name
    invoice.maintenance_period = period
    invoice.append("items", {
        "item_code": item_code,
        "qty": 1,
        "rate": amount,
        "description": description,
    })
    invoice.insert(ignore_permissions=True)
    invoice.submit()
