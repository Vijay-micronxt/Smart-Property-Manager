"""Money: raising invoices and recording what the customer paid.

A confirmed booking already carries its payment plan (one Payment Plan row per
milestone). What the desk does from there -- and what this module does over
JSON -- is:

    payment plan milestone  --generate_invoice-->  Sales Invoice (submitted)
    Sales Invoice           --record_payment---->  Payment Entry (submitted)

plus ad-hoc charges (registration, corner premium, club membership …) that
are not part of the plan: ``create_invoice``.

Who may do it is the doctype permission, not this module: Property Manager
and ERPNext's Accounts User can raise and collect, sales staff can only read.
The app should hide the buttons using ``session.whoami().permissions``.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, today

from property_core.api.crm import base
from property_core.api.utils import ok

INVOICE_FIELDS = [
    "name",
    "customer",
    "customer_name",
    "posting_date",
    "due_date",
    "grand_total",
    "outstanding_amount",
    "status",
    "docstatus",
    "is_return",
    "remarks",
    "company",
]

PAYMENT_FIELDS = [
    "name",
    "party",
    "party_name",
    "posting_date",
    "paid_amount",
    "mode_of_payment",
    "reference_no",
    "reference_date",
    "docstatus",
    "unallocated_amount",
]


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def options():
    """What a payment screen needs: modes of payment and the sale items an
    ad-hoc charge can be raised against."""
    base.require_user()
    settings = frappe.get_cached_doc("Property Core Settings")
    return ok(
        data={
            "modes_of_payment": frappe.get_all(
                "Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name asc"
            ),
            "default_items": {
                "sale": settings.get("sale_item_code"),
                "rent": settings.get("rent_item_code"),
                "late_fee": settings.get("late_fee_item_code"),
            },
            "charge_items": frappe.get_all(
                "Item",
                filters={"disabled": 0, "is_sales_item": 1, "is_stock_item": 0},
                fields=["name", "item_name", "standard_rate"],
                order_by="item_name asc",
                limit=200,
            ),
            "company": _company(),
            "currency": frappe.db.get_default("currency"),
        }
    )


@frappe.whitelist()
def get_invoices(
    customer=None,
    booking=None,
    property_unit=None,
    status=None,
    overdue=None,
    from_date=None,
    to_date=None,
    search=None,
    page=1,
    page_size=20,
    order_by=None,
):
    """Sales Invoices. ``booking`` = every invoice raised for that deal (its
    milestones plus anything billed on its unit to its customer, e.g.
    maintenance and ad-hoc charges)."""
    base.require_user()
    conditions = [["docstatus", "<", 2]]
    if customer:
        conditions.append(["customer", "=", customer])
    if booking:
        conditions.append(["name", "in", invoices_of_booking(booking) or [""]])
    if property_unit and _invoice_has_unit():
        conditions.append(["property_unit", "=", property_unit])
    if status:
        values = base.parse(status, default=status)
        conditions.append(["status", "in", values if isinstance(values, list) else [values]])
    if base.as_bool(overdue):
        conditions += [["outstanding_amount", ">", 0], ["due_date", "<", today()], ["docstatus", "=", 1]]
    base.date_range(conditions, "posting_date", from_date, to_date)

    fields = INVOICE_FIELDS + (["property_unit"] if _invoice_has_unit() else [])
    result = base.listing(
        "Sales Invoice",
        fields,
        extra_filters=conditions,
        search=search,
        search_fields=["name", "customer_name"],
        order_by=order_by or "posting_date desc",
        page=page,
        page_size=page_size,
    )
    return ok(data=result)


@frappe.whitelist()
def get_invoice(name):
    doc = base.read_doc("Sales Invoice", name)
    payload = base.doc_payload(doc)
    payload["milestone"] = frappe.db.get_value(
        "Payment Plan", {"invoice": name}, ["name", "booking", "milestone", "due_date"], as_dict=True
    )
    payload["payments"] = _payments_against(name)
    return ok(data=base.serialize(payload))


@frappe.whitelist()
def get_payments(customer=None, booking=None, invoice=None, from_date=None, to_date=None, page=1, page_size=20):
    base.require_user()
    conditions = [["docstatus", "<", 2], ["payment_type", "=", "Receive"]]
    if customer:
        conditions.append(["party", "=", customer])
    invoices = []
    if booking:
        invoices = invoices_of_booking(booking)
    if invoice:
        invoices = [invoice]
    if booking or invoice:
        names = frappe.get_list(
            "Payment Entry Reference",
            filters={"reference_doctype": "Sales Invoice", "reference_name": ["in", invoices or [""]]},
            pluck="parent",
            ignore_permissions=True,
        )
        if booking:
            customer_of = frappe.db.get_value("Property Booking", booking, "customer")
            # advances taken for the booking before any invoice existed
            names += frappe.get_list(
                "Payment Entry",
                filters={"party": customer_of, "unallocated_amount": [">", 0], "docstatus": 1},
                pluck="name",
            )
        conditions.append(["name", "in", list(set(names)) or [""]])
    base.date_range(conditions, "posting_date", from_date, to_date)

    return ok(
        data=base.listing(
            "Payment Entry",
            PAYMENT_FIELDS,
            extra_filters=conditions,
            order_by="posting_date desc",
            page=page,
            page_size=page_size,
        )
    )


@frappe.whitelist()
def get_payment(name):
    return ok(data=base.doc_payload(base.read_doc("Payment Entry", name)))


@frappe.whitelist()
def statement(booking):
    """Everything money about one booking: plan, invoices, payments, totals --
    the customer's ledger for that deal."""
    from property_core.api.crm.bookings import collections_for, payment_plan_rows

    doc = base.read_doc("Property Booking", booking)
    invoices = invoices_of_booking(booking)
    rows = []
    if invoices and base.can_read("Sales Invoice"):
        rows = frappe.get_list(
            "Sales Invoice",
            filters={"name": ["in", invoices], "docstatus": 1},
            fields=INVOICE_FIELDS,
            order_by="posting_date asc",
        )
    payments = []
    for invoice in invoices:
        payments += _payments_against(invoice)
    return ok(
        data={
            "booking": booking,
            "customer": doc.customer,
            "total_price": flt(doc.total_price, 2),
            "plan": payment_plan_rows(booking),
            "plan_totals": collections_for(booking),
            "invoices": base.serialize(rows),
            "payments": base.serialize(sorted(payments, key=lambda p: str(p.get("posting_date")))),
            "billed": flt(sum(flt(r.grand_total) for r in rows), 2),
            "outstanding": flt(sum(flt(r.outstanding_amount) for r in rows), 2),
            "unbilled": flt(
                sum(flt(r["amount"]) for r in payment_plan_rows(booking) if not r.get("invoice")), 2
            ),
        }
    )


# --------------------------------------------------------------------------- #
# raising invoices
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def generate_invoice(payment_plan):
    """Bill one milestone of a booking's payment plan (the desk's "Generate
    Invoice" button on Payment Plan)."""
    _require("Sales Invoice", "create")
    plan = base.read_doc("Payment Plan", payment_plan)
    if plan.invoice:
        return ok(data={"payment_plan": plan.name, "invoice": plan.invoice}, message=_("Already invoiced"))
    invoice = plan.generate_invoice()
    return ok(
        data={"payment_plan": plan.name, "invoice": invoice, **_invoice_brief(invoice)},
        message=_("Invoice {0} raised").format(invoice),
    )


@frappe.whitelist()
def generate_due_invoices(booking, upto_date=None):
    """Bill every milestone of a booking that is due by ``upto_date``
    (default today) and not invoiced yet."""
    _require("Sales Invoice", "create")
    base.read_doc("Property Booking", booking)
    upto = getdate(upto_date or today())
    raised, failed = [], []
    for row in frappe.get_all(
        "Payment Plan",
        filters={"booking": booking, "invoice": ["is", "not set"], "due_date": ["<=", upto]},
        pluck="name",
        order_by="due_date asc",
    ):
        try:
            raised.append({"payment_plan": row, "invoice": frappe.get_doc("Payment Plan", row).generate_invoice()})
        except Exception as e:
            failed.append({"payment_plan": row, "error": str(e)})
    return ok(
        data={"raised": raised, "failed": failed},
        message=_("{0} invoice(s) raised").format(len(raised)),
    )


@frappe.whitelist()
def create_invoice(customer=None, items=None, booking=None, property_unit=None, due_date=None, submit=1, remarks=None):
    """An ad-hoc charge outside the payment plan.

    ``items``: ``[{"item_code": "...", "rate": 50000, "qty": 1, "description": "Corner premium"}]``.
    ``item_code`` may be left out -- the Default Sale Item from Property Core
    Settings is used. With ``booking``, customer and unit come off the booking.
    """
    _require("Sales Invoice", "create")
    if booking:
        b = base.read_doc("Property Booking", booking)
        customer = customer or b.customer
        property_unit = property_unit or b.property_unit
    if not customer:
        frappe.throw(_("An invoice needs a customer or a booking"), frappe.MandatoryError)

    items = base.parse(items, default=[]) or []
    if not items:
        frappe.throw(_("Add at least one charge"), frappe.MandatoryError)

    default_item = frappe.db.get_single_value("Property Core Settings", "sale_item_code")
    invoice = frappe.new_doc("Sales Invoice")
    invoice.customer = customer
    invoice.company = _company()
    invoice.posting_date = nowdate()
    invoice.set_posting_time = 1
    invoice.due_date = max(getdate(due_date), getdate(nowdate())) if due_date else nowdate()
    if remarks:
        invoice.remarks = remarks
    if property_unit and invoice.meta.has_field("property_unit"):
        invoice.property_unit = property_unit
    for row in items:
        item_code = row.get("item_code") or default_item
        if not item_code:
            frappe.throw(_("No item on a charge and no Default Sale Item in Property Core Settings"))
        invoice.append(
            "items",
            {
                "item_code": item_code,
                "qty": flt(row.get("qty")) or 1,
                "rate": flt(row.get("rate")),
                "description": row.get("description") or item_code,
            },
        )
    invoice.insert()
    if base.as_bool(submit, True):
        invoice.submit()
    return ok(data=_invoice_brief(invoice.name), message=_("Invoice {0} raised").format(invoice.name))


@frappe.whitelist()
def submit_invoice(name):
    doc = base.read_doc("Sales Invoice", name)
    doc.check_permission("submit")
    if doc.docstatus == 0:
        doc.submit()
    return ok(data=_invoice_brief(name), message=_("Invoice {0} submitted").format(name))


@frappe.whitelist()
def cancel_invoice(name, reason=None):
    doc = base.read_doc("Sales Invoice", name)
    doc.check_permission("cancel")
    doc.cancel()
    # the milestone goes back to "to bill", so it can be invoiced again
    for row in frappe.get_all("Payment Plan", filters={"invoice": name}, pluck="name"):
        frappe.db.set_value("Payment Plan", row, {"invoice": None, "payment_status": "Pending"})
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(data=_invoice_brief(name), message=_("Invoice {0} cancelled").format(name))


# --------------------------------------------------------------------------- #
# collecting
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def record_payment(
    amount,
    mode_of_payment,
    invoice=None,
    booking=None,
    customer=None,
    posting_date=None,
    reference_no=None,
    reference_date=None,
    remarks=None,
    submit=1,
    tds_amount=None,
):
    """Money received. Three ways to aim it:

    * ``invoice``  -- against that invoice
    * ``booking``  -- spread over the booking's open invoices, oldest due first;
                      whatever is left stays on the customer as an advance
    * ``customer`` -- an advance with no invoice (e.g. token amount at booking)

    Bank / UPI / cheque modes need ``reference_no`` and ``reference_date``
    (ERPNext refuses a bank receipt without them).

    ``tds_amount`` -- TDS the buyer deducted (India 194-IA). ``amount`` is what
    actually reached the bank; the invoice is settled for amount + TDS and the
    TDS goes to the Buyer TDS Receivable Account in Property Core Settings.
    ``tds_suggestion`` works out the split.
    """
    _require("Payment Entry", "create")
    amount = flt(amount)
    tds_amount = flt(tds_amount)
    if amount <= 0:
        frappe.throw(_("Amount must be more than zero"))
    tds_account = None
    if tds_amount:
        from property_core.property_core.utils import settings

        tds_account = settings.get("buyer_tds_account")
        if not tds_account:
            frappe.throw(_("Set Buyer TDS Receivable Account in Property Core Settings to record TDS"))

    targets = []  # [(invoice, outstanding)]
    if invoice:
        inv = base.read_doc("Sales Invoice", invoice)
        if inv.docstatus != 1:
            frappe.throw(_("Invoice {0} is not submitted").format(invoice))
        customer = inv.customer
        targets = [(inv.name, flt(inv.outstanding_amount))]
    elif booking:
        b = base.read_doc("Property Booking", booking)
        customer = b.customer
        open_invoices = frappe.get_all(
            "Sales Invoice",
            filters={"name": ["in", invoices_of_booking(booking) or [""]], "docstatus": 1, "outstanding_amount": [">", 0]},
            fields=["name", "outstanding_amount"],
            order_by="due_date asc, posting_date asc",
        )
        targets = [(r.name, flt(r.outstanding_amount)) for r in open_invoices]
    elif customer:
        base.read_doc("Customer", customer)
    else:
        frappe.throw(_("Say what the payment is for: invoice, booking or customer"), frappe.MandatoryError)

    company = frappe.db.get_value("Sales Invoice", targets[0][0], "company") if targets else _company()
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
    from erpnext.accounts.party import get_party_account

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.company = company
    pe.posting_date = posting_date or nowdate()
    pe.mode_of_payment = mode_of_payment
    pe.party_type = "Customer"
    pe.party = customer
    pe.paid_from = get_party_account("Customer", customer, company)
    pe.paid_to = get_bank_cash_account(mode_of_payment, company)["account"]
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.reference_no = reference_no
    pe.reference_date = reference_date or (pe.posting_date if reference_no else None)
    if remarks:
        pe.remarks = remarks

    if tds_amount:
        pe.append("deductions", {
            "account": tds_account,
            "cost_center": frappe.get_cached_value("Company", company, "cost_center"),
            "amount": tds_amount,
            "description": _("TDS deducted by buyer"),
        })

    left = amount + tds_amount
    for name, outstanding in targets:
        if left <= 0:
            break
        allocate = min(left, outstanding)
        pe.append(
            "references",
            {"reference_doctype": "Sales Invoice", "reference_name": name, "allocated_amount": allocate},
        )
        left -= allocate

    if not targets and pe.meta.has_field("custom_skip_auto_reconcile"):
        # an advance on purpose (a token before the booking exists) must stay an
        # advance -- auto-reconciliation would spend it on whatever invoice of
        # the customer happens to be open, and the booking amount it was meant
        # for would then show unpaid
        pe.custom_skip_auto_reconcile = 1

    pe.setup_party_account_field()
    pe.set_missing_values()
    pe.set_missing_ref_details(force=True)
    pe.insert()
    if base.as_bool(submit, True):
        pe.submit()

    return ok(
        data={
            "name": pe.name,
            "docstatus": pe.docstatus,
            "paid_amount": flt(pe.paid_amount, 2),
            "allocated": [
                {"invoice": r.reference_name, "amount": flt(r.allocated_amount, 2)} for r in pe.references
            ],
            "advance": flt(pe.unallocated_amount, 2),
        },
        message=_("Payment {0} recorded").format(pe.name),
    )


@frappe.whitelist()
def tds_suggestion(invoice=None, booking=None):
    """How a receipt splits when the buyer deducts TDS: on an outstanding of X,
    the bank gets X less rate%, and the rest is TDS. Applies only when the
    booking's agreement value reaches the threshold in settings."""
    from property_core.property_core.utils import settings

    rate = settings.get("buyer_tds_rate")
    threshold = settings.get("buyer_tds_threshold")
    if invoice:
        inv = base.read_doc("Sales Invoice", invoice)
        outstanding = flt(inv.outstanding_amount)
        booking = booking or frappe.db.get_value("Payment Plan", {"invoice": invoice}, "booking")
    elif booking:
        base.read_doc("Property Booking", booking)
        # instalments only -- 194-IA is on the property price, not maintenance
        plan_invoices = [
            i for i in frappe.get_all("Payment Plan", filters={"booking": booking}, pluck="invoice") if i
        ]
        outstanding = sum(
            flt(r.outstanding_amount)
            for r in frappe.get_all(
                "Sales Invoice",
                filters={"name": ["in", plan_invoices or [""]], "docstatus": 1},
                fields=["outstanding_amount"],
            )
        )
    else:
        frappe.throw(_("Give an invoice or a booking"), frappe.MandatoryError)

    agreement_value = flt(frappe.db.get_value("Property Booking", booking, "total_price")) if booking else 0
    applies = bool(settings.get("buyer_tds_account")) and rate > 0 and (
        not threshold or agreement_value >= threshold
    )
    tds = flt(outstanding * rate / 100, 2) if applies else 0
    return ok(data={
        "applies": applies,
        "rate": rate,
        "threshold": threshold,
        "agreement_value": agreement_value,
        "outstanding": flt(outstanding, 2),
        "tds_amount": tds,
        "amount": flt(outstanding - tds, 2),
    })


@frappe.whitelist()
def cancel_payment(name, reason=None):
    doc = base.read_doc("Payment Entry", name)
    doc.check_permission("cancel")
    doc.cancel()
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(data={"name": name, "docstatus": doc.docstatus}, message=_("Payment cancelled"))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def invoices_of_booking(booking):
    """Milestone invoices of the booking, plus invoices on its unit to its
    customer (maintenance, ad-hoc charges)."""
    names = [i for i in frappe.get_all("Payment Plan", filters={"booking": booking}, pluck="invoice") if i]
    names += [
        i for i in frappe.get_all("Payment Plan", filters={"booking": booking}, pluck="late_fee_invoice") if i
    ]
    if _invoice_has_unit():
        unit, customer = frappe.db.get_value("Property Booking", booking, ["property_unit", "customer"])
        names += frappe.get_all(
            "Sales Invoice", filters={"property_unit": unit, "customer": customer}, pluck="name"
        )
    return list(dict.fromkeys(names))


def _payments_against(invoice):
    if not base.can_read("Payment Entry"):
        return []
    return frappe.get_list(
        "Payment Entry",
        filters=[
            ["Payment Entry Reference", "reference_doctype", "=", "Sales Invoice"],
            ["Payment Entry Reference", "reference_name", "=", invoice],
            ["docstatus", "=", 1],
        ],
        fields=[
            "name",
            "posting_date",
            "mode_of_payment",
            "reference_no",
            "`tabPayment Entry Reference`.allocated_amount as allocated_amount",
        ],
    )


def _invoice_brief(name):
    return base.serialize(
        frappe.db.get_value(
            "Sales Invoice", name, ["name", "docstatus", "status", "grand_total", "outstanding_amount", "due_date"], as_dict=True
        )
        or {}
    )


def _invoice_has_unit():
    return frappe.get_meta("Sales Invoice").has_field("property_unit")


def _company():
    return (
        frappe.db.get_single_value("Property Core Settings", "default_company")
        or frappe.defaults.get_user_default("company")
        or frappe.db.get_default("company")
    )


def _require(doctype, ptype):
    base.require_user()
    if not frappe.has_permission(doctype, ptype):
        frappe.throw(_("Not permitted to {0} {1}").format(ptype, _(doctype)), frappe.PermissionError)
