import frappe
from frappe.utils import getdate, today


def run_daily_payment_plan_billing():
    """Scheduled daily job -- auto-generates the Sales Invoice for any Payment
    Plan milestone once its due date arrives, so the Sale side gets the same
    automatic invoicing the Lease/Rent side already has via billing_engine.py.
    Reuses Payment Plan's own generate_invoice() rather than duplicating it.
    """
    today_date = getdate(today())

    plans = frappe.get_all(
        "Payment Plan",
        filters={
            "payment_status": "Pending",
            "due_date": ["<=", today_date],
            "invoice": ["in", ["", None]],
        },
        fields=["name"],
    )

    for plan in plans:
        try:
            doc = frappe.get_doc("Payment Plan", plan.name)
            doc.generate_invoice()
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Payment Plan Auto-Invoice Error: {plan.name}")

    frappe.db.commit()
