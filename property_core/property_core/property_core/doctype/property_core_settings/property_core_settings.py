import frappe
from frappe.model.document import Document


class PropertyCoreSettings(Document):
    def validate(self):
        if self.security_deposit_account:
            account_type = frappe.db.get_value("Account", self.security_deposit_account, "account_type")
            if account_type not in ("Payable", "Liability", None):
                frappe.msgprint(
                    frappe._("Security Deposit Account should be a Liability account."),
                    indicator="orange",
                    alert=True,
                )
