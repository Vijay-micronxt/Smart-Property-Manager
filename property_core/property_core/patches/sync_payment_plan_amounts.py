"""Fill Paid / Outstanding on every instalment and correct its status from the
invoice -- instalments paid by cash, cheque or NEFT were still "Invoiced"."""

import frappe

from property_core.property_core.utils.plan_status import sync_plan


def execute():
    frappe.reload_doc("property_core", "doctype", "payment_plan")
    for name in frappe.get_all("Payment Plan", pluck="name"):
        sync_plan(name)
