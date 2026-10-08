"""Paying commission out -- in the books, not just as a status.

A Commission Settlement used to flip its entries to Settled and stop there:
no expense was booked, nothing was owed to anyone in the ledger, and the
payment_entry link was filled in by hand if at all. Who was paid how much
could not be read from the accounts.

When Property Core Settings has a Commission Expense Account, submitting a
settlement books it against the sales person's payee:

  * Employee        -- Journal Entry: expense Dr / Commission Payable Cr against
                       the Employee. Paid later with a Payment Entry (Pay,
                       party Employee) against that Journal Entry.
  * Channel Partner -- a draft Purchase Invoice from the Supplier for the
                       brokerage item. Accounts add the broker's GST and bill
                       number and submit it; TDS (194H) comes from the
                       Supplier's Tax Withholding Category. Paid like any bill.

The settlement turns Paid once that Journal Entry / Purchase Invoice is
settled. Without an expense account the settlement stays status-only, as before.
"""

import frappe
from frappe import _
from frappe.utils import flt

from property_core.property_core.utils import settings

SALES_PERSON_FIELDS = [
    {
        "fieldname": "custom_commission_payee_type",
        "fieldtype": "Select",
        "label": "Commission Paid To",
        "options": "\nEmployee\nChannel Partner",
        "insert_after": "employee",
        "description": "Employee: booked by Journal Entry against the Employee above. "
        "Channel Partner: billed as a Purchase Invoice from the Supplier below.",
    },
    {
        "fieldname": "custom_commission_supplier",
        "fieldtype": "Link",
        "label": "Channel Partner (Supplier)",
        "options": "Supplier",
        "insert_after": "custom_commission_payee_type",
        "depends_on": "eval:doc.custom_commission_payee_type=='Channel Partner'",
        "mandatory_depends_on": "eval:doc.custom_commission_payee_type=='Channel Partner'",
    },
]


def sync_sales_person_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields({"Sales Person": SALES_PERSON_FIELDS}, ignore_validate=True, update=True)


def delete_sales_person_fields():
    for field in SALES_PERSON_FIELDS:
        name = frappe.db.get_value("Custom Field", {"dt": "Sales Person", "fieldname": field["fieldname"]})
        if name:
            frappe.delete_doc("Custom Field", name, ignore_permissions=True)


def resolve_payee(sales_person):
    sp = frappe.db.get_value(
        "Sales Person", sales_person,
        ["employee", "custom_commission_payee_type", "custom_commission_supplier"]
        if frappe.db.has_column("Sales Person", "custom_commission_payee_type") else ["employee"],
        as_dict=True,
    ) or {}
    payee_type = sp.get("custom_commission_payee_type") or ("Employee" if sp.get("employee") else None)
    return frappe._dict(
        payee_type=payee_type,
        employee=sp.get("employee") if payee_type == "Employee" else None,
        supplier=sp.get("custom_commission_supplier") if payee_type == "Channel Partner" else None,
    )


def book(settlement):
    """Book a submitted settlement. No-op without a Commission Expense Account."""
    expense_account = settings.get("commission_expense_account")
    if not expense_account:
        return

    payee = resolve_payee(settlement.sales_person)
    company = frappe.db.get_value("Account", expense_account, "company")
    cost_center = frappe.get_cached_value("Company", company, "cost_center")
    remark = _("Commission settlement {0} for {1}").format(settlement.name, settlement.sales_person)

    if payee.payee_type == "Employee":
        if not payee.employee:
            frappe.throw(_("Sales Person {0} has no Employee to pay commission to").format(settlement.sales_person))
        payable_account = settings.get("commission_payable_account")
        if not payable_account:
            frappe.throw(_("Set Commission Payable Account (Employees) in Property Core Settings"))

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = company
        je.posting_date = settlement.settlement_date
        je.user_remark = remark
        je.append("accounts", {
            "account": expense_account,
            "debit_in_account_currency": flt(settlement.total_amount),
            "cost_center": cost_center,
        })
        je.append("accounts", {
            "account": payable_account,
            "party_type": "Employee",
            "party": payee.employee,
            "credit_in_account_currency": flt(settlement.total_amount),
            "cost_center": cost_center,
        })
        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        settlement.db_set({"payee_type": "Employee", "employee": payee.employee, "journal_entry": je.name})

    elif payee.payee_type == "Channel Partner":
        if not payee.supplier:
            frappe.throw(_("Sales Person {0} has no Channel Partner Supplier").format(settlement.sales_person))
        item = settings.get("commission_item")
        if not item:
            frappe.throw(_("Set Brokerage Item (Channel Partners) in Property Core Settings"))

        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = payee.supplier
        pi.company = company
        pi.posting_date = settlement.settlement_date
        pi.remarks = remark
        if frappe.db.get_value("Supplier", payee.supplier, "tax_withholding_category"):
            pi.apply_tds = 1
        pi.append("items", {
            "item_code": item,
            "description": remark,
            "qty": 1,
            "rate": flt(settlement.total_amount),
            "expense_account": expense_account,
            "cost_center": cost_center,
        })
        pi.flags.ignore_permissions = True
        # draft: the broker's GST and bill number come off their actual bill
        pi.insert()
        settlement.db_set({"payee_type": "Channel Partner", "supplier": payee.supplier, "purchase_invoice": pi.name})

    else:
        frappe.throw(
            _("Set 'Commission Paid To' on Sales Person {0} (Employee or Channel Partner)").format(
                settlement.sales_person
            )
        )


def unbook(settlement):
    if settlement.journal_entry:
        je = frappe.get_doc("Journal Entry", settlement.journal_entry)
        if je.docstatus == 1:
            je.flags.ignore_permissions = True
            je.cancel()
    if settlement.purchase_invoice:
        pi = frappe.get_doc("Purchase Invoice", settlement.purchase_invoice)
        if pi.docstatus == 0:
            settlement.db_set("purchase_invoice", None)
            frappe.delete_doc("Purchase Invoice", pi.name, ignore_permissions=True)
        elif pi.docstatus == 1:
            pi.flags.ignore_permissions = True
            pi.cancel()


def refresh_paid(settlement_name):
    s = frappe.db.get_value(
        "Commission Settlement", settlement_name,
        ["docstatus", "status", "journal_entry", "purchase_invoice"], as_dict=True,
    )
    if not s or s.docstatus != 1:
        return

    paid = False
    if s.purchase_invoice:
        pi = frappe.db.get_value("Purchase Invoice", s.purchase_invoice, ["docstatus", "outstanding_amount"], as_dict=True)
        paid = bool(pi and pi.docstatus == 1 and flt(pi.outstanding_amount) <= 0.005)
    elif s.journal_entry:
        # what is still owed on the JE: its own credit plus payments against it
        owed = frappe.db.sql(
            """select sum(amount) from `tabPayment Ledger Entry`
            where against_voucher_type='Journal Entry' and against_voucher_no=%s and delinked=0""",
            s.journal_entry,
        )[0][0]
        paid = abs(flt(owed)) <= 0.005

    status = "Paid" if paid else "Submitted"
    if status != s.status:
        frappe.db.set_value("Commission Settlement", settlement_name, "status", status, update_modified=False)


def on_payment_entry(doc, method=None):
    for row in doc.get("references") or []:
        field = {"Purchase Invoice": "purchase_invoice", "Journal Entry": "journal_entry"}.get(row.reference_doctype)
        if not field:
            continue
        for name in frappe.get_all("Commission Settlement", filters={field: row.reference_name}, pluck="name"):
            refresh_paid(name)


def run_daily_sync():
    for name in frappe.get_all("Commission Settlement", filters={"docstatus": 1, "status": "Submitted"}, pluck="name"):
        refresh_paid(name)
