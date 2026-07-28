import frappe
from frappe.model.document import Document
from frappe.utils import today


class PropertyAgreement(Document):
    def validate(self):
        self.validate_dates()

    def validate_dates(self):
        if self.end_date and self.start_date and self.end_date < self.start_date:
            frappe.throw(frappe._("End Date cannot be before Start Date"))

    def on_update(self):
        pass


@frappe.whitelist()
def record_security_deposit(agreement_name):
    doc = frappe.get_doc("Property Agreement", agreement_name)

    if doc.security_deposit_journal:
        frappe.throw(frappe._("Security deposit journal entry already exists: {0}").format(
            doc.security_deposit_journal
        ))

    if not doc.security_deposit_amount or doc.security_deposit_amount <= 0:
        frappe.throw(frappe._("Please set a Security Deposit Amount before recording the deposit"))

    settings = frappe.get_single("Property Core Settings")
    if not settings.security_deposit_account:
        frappe.throw(
            frappe._("Please configure 'Security Deposit Account' in Property Core Settings")
        )
    if not settings.default_company:
        frappe.throw(frappe._("Please configure 'Default Company' in Property Core Settings"))

    company = settings.default_company

    try:
        from erpnext.accounts.party import get_party_account
        receivable_account = get_party_account("Customer", doc.customer, company)
    except Exception:
        frappe.throw(
            frappe._("Could not determine receivable account for customer {0}. "
                     "Ensure ERPNext is configured correctly.").format(doc.customer)
        )

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.posting_date = doc.signed_date or today()
    je.company = company
    je.remark = frappe._("Security deposit for agreement {0} — {1}").format(
        doc.name, doc.customer
    )
    je.user_remark = je.remark

    # Debit: Customer receivable — they owe us the deposit
    je.append("accounts", {
        "account": receivable_account,
        "party_type": "Customer",
        "party": doc.customer,
        "debit_in_account_currency": doc.security_deposit_amount,
        "reference_type": "Property Agreement",
        "reference_name": doc.name,
    })

    # Credit: Security deposit liability — we hold it until refund
    je.append("accounts", {
        "account": settings.security_deposit_account,
        "credit_in_account_currency": doc.security_deposit_amount,
        "reference_type": "Property Agreement",
        "reference_name": doc.name,
    })

    je.insert(ignore_permissions=True)
    je.submit()

    frappe.db.set_value("Property Agreement", doc.name, {
        "security_deposit_journal": je.name,
        "security_deposit_received": 1,
    })

    return je.name


@frappe.whitelist()
def refund_security_deposit(agreement_name):
    doc = frappe.get_doc("Property Agreement", agreement_name)

    if not doc.security_deposit_journal:
        frappe.throw(frappe._("No deposit journal entry found to reverse"))

    je = frappe.get_doc("Journal Entry", doc.security_deposit_journal)
    if je.docstatus != 1:
        frappe.throw(frappe._("Deposit journal entry is not submitted"))

    je.cancel()

    frappe.db.set_value("Property Agreement", doc.name, {
        "security_deposit_received": 0,
    })

    return doc.security_deposit_journal
