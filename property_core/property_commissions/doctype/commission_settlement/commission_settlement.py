import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CommissionSettlement(Document):
    def before_validate(self):
        self.total_amount = sum(flt(row.commission_amount) for row in self.commission_entries)

    def validate(self):
        if not self.commission_entries:
            frappe.throw(_("Add at least one Commission Entry to settle"))
        self._validate_entries()
        if flt(self.total_amount) <= 0:
            frappe.throw(
                _("The settlement totals {0}: commission to recover is more than commission payable. "
                  "Settle it with the sales person's next payable commission.").format(
                    frappe.format_value(self.total_amount, {"fieldtype": "Currency"})
                )
            )

    def _validate_entries(self):
        seen = set()
        for row in self.commission_entries:
            if row.commission_entry in seen:
                frappe.throw(_("Commission Entry {0} is in the table twice").format(row.commission_entry))
            seen.add(row.commission_entry)

            entry = frappe.db.get_value(
                "Commission Entry", row.commission_entry,
                ["sales_person", "status", "payable_amount"], as_dict=True,
            )
            if entry.sales_person != self.sales_person:
                frappe.throw(
                    _("Commission Entry {0} belongs to a different Sales Person ({1}).").format(
                        row.commission_entry, entry.sales_person
                    )
                )
            if entry.status in ("Settled", "Cancelled"):
                frappe.throw(_("Commission Entry {0} is {1}").format(row.commission_entry, entry.status))

            payable = flt(entry.payable_amount)
            amount = flt(row.commission_amount)
            # payable now is the cap; on a clawback both are negative
            within = (0 < amount <= payable + 0.005) if payable > 0 else (payable - 0.005 <= amount < 0)
            if not within:
                frappe.throw(
                    _("Row {0}: {1} can be settled for at most {2} now").format(
                        row.idx, row.commission_entry,
                        frappe.format_value(payable, {"fieldtype": "Currency"}),
                    )
                )

    def on_submit(self):
        self._apply(+1)
        self.db_set("status", "Submitted")

        from property_core.property_commissions import payout

        payout.book(self)
        payout.refresh_paid(self.name)

    def on_cancel(self):
        from property_core.property_commissions import payout

        payout.unbook(self)
        self._apply(-1)
        self.db_set("status", "Cancelled")

    def _apply(self, sign):
        from property_core.property_commissions.doctype.commission_entry.commission_entry import (
            refresh_for_booking,
        )

        bookings = set()
        for row in self.commission_entries:
            settled = flt(frappe.db.get_value("Commission Entry", row.commission_entry, "settled_amount"))
            frappe.db.set_value(
                "Commission Entry", row.commission_entry,
                {
                    "settled_amount": flt(settled + sign * flt(row.commission_amount), 2),
                    "settlement": self.name if sign > 0 else None,
                },
                update_modified=False,
            )
            bookings.add(frappe.db.get_value("Commission Entry", row.commission_entry, "booking"))
        for booking in bookings:
            refresh_for_booking(booking)


@frappe.whitelist()
def get_pending_entries(sales_person):
    """Entries with something to settle now, for the settlement table:
    commission released and not yet paid, and (negative) commission to
    recover on cancelled bookings. ``commission_amount`` is the amount payable
    now, which is what the settlement row takes."""
    frappe.has_permission("Commission Settlement", "create", throw=True)
    rows = frappe.get_all(
        "Commission Entry",
        filters={
            "sales_person": sales_person,
            "status": ["in", ["Pending", "Partly Settled", "Clawback"]],
            "payable_amount": ["!=", 0],
        },
        fields=["name", "booking", "property_unit", "payable_amount", "commission_amount as total_commission",
                "commission_date", "status"],
        order_by="commission_date asc",
    )
    for row in rows:
        row["commission_amount"] = row.pop("payable_amount")
    return rows
