"""Property Booking — the deal itself, its payment plan and what has been
collected against it.

Submitting a booking is what actually takes the unit off the market, raises
the payment plan, provisions the customer's portal login and starts
maintenance billing. So ``submit_booking`` is a real step, not a formality,
and it is kept separate from ``create_booking`` on purpose: a draft can be
corrected, a submitted booking cannot.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "customer",
    "property_unit",
    "unit_property",
    "project",
    "unit_type",
    "unit_area",
    "booking_status",
    "booking_date",
    "total_price",
    "booking_amount",
    "payment_plan_template",
    "sales_person",
    "opportunity",
    "lead",
    "docstatus",
    "owner",
    "creation",
]

WRITABLE = {
    "customer",
    "property_unit",
    "unit_property",
    "project",
    "total_price",
    "booking_amount",
    "booking_date",
    "payment_plan_template",
    "sales_person",
    "opportunity",
    "lead",
    "notes",
}


@frappe.whitelist()
def get_bookings(
    search=None,
    customer=None,
    property=None,
    project=None,
    property_unit=None,
    status=None,
    docstatus=None,
    mine=None,
    from_date=None,
    to_date=None,
    filters=None,
    order_by=None,
    page=1,
    page_size=20,
):
    user = base.require_user()

    conditions = []
    if customer:
        conditions.append(["customer", "=", customer])
    if property:
        conditions.append(["unit_property", "=", property])
    if project:
        conditions.append(["project", "=", project])
    if property_unit:
        conditions.append(["property_unit", "=", property_unit])
    if status:
        values = base.parse(status, default=status)
        conditions.append(["booking_status", "in", values if isinstance(values, list) else [values]])
    if docstatus is not None and docstatus != "":
        conditions.append(["docstatus", "=", int(docstatus)])
    else:
        conditions.append(["docstatus", "<", 2])
    if base.as_bool(mine):
        conditions.append(["owner", "=", user])
    base.date_range(conditions, "booking_date", from_date, to_date)

    result = base.listing(
        "Property Booking",
        LIST_FIELDS,
        filters=filters,
        extra_filters=conditions,
        search=search,
        search_fields=["name", "customer", "property_unit"],
        order_by=order_by or "booking_date desc",
        page=page,
        page_size=page_size,
    )
    return ok(data=result)


@frappe.whitelist()
def get_booking(name):
    """The booking with its money attached — plan, invoices, what is paid."""
    doc = base.read_doc("Property Booking", name)
    payload = base.doc_payload(doc)

    payload["unit"] = base.serialize(
        frappe.db.get_value(
            "Property Unit",
            doc.property_unit,
            ["name", "unit_number", "property", "project", "unit_type", "area", "facing", "availability_status"],
            as_dict=True,
        )
    )
    payload["customer_name"] = frappe.db.get_value("Customer", doc.customer, "customer_name")
    payload["payment_plan"] = payment_plan_rows(name)
    payload["collections"] = collections_for(name)
    payload["follow_ups"] = base.serialize(
        frappe.get_list(
            "Property Follow Up",
            filters={"reference_doctype": "Property Booking", "reference_name": name},
            fields=["name", "follow_up_type", "status", "scheduled_on", "assigned_to", "outcome"],
            order_by="scheduled_on desc",
            limit=10,
        )
    )
    return ok(data=payload)


@frappe.whitelist()
def create_booking(data=None, submit=0, **kwargs):
    """A booking raised straight off a unit — the walk-in path, where nobody
    ever logged a lead."""
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})

    if not payload.get("property_unit"):
        frappe.throw(_("A booking needs a unit"))
    if not payload.get("customer"):
        frappe.throw(_("A booking needs a customer"))

    unit = frappe.db.get_value(
        "Property Unit", payload["property_unit"], ["property", "base_price"], as_dict=True
    )
    defaults = {
        "unit_property": payload.get("unit_property") or (unit.property if unit else None),
        "booking_date": payload.get("booking_date") or today(),
        "total_price": payload.get("total_price") or (unit.base_price if unit else 0),
    }

    doc = base.create_doc("Property Booking", payload, WRITABLE, defaults=defaults)
    if base.as_bool(submit):
        doc.submit()

    return ok(data=base.doc_payload(doc), message=_("Booking {0} created").format(doc.name))


@frappe.whitelist()
def update_booking(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})
    doc, changed = base.write_doc("Property Booking", name, payload, WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def submit_booking(name):
    """Confirm the deal: the unit is reserved, the payment plan is raised, the
    customer gets a portal login and maintenance starts."""
    doc = base.read_doc("Property Booking", name)
    doc.check_permission("submit")

    if doc.docstatus == 1:
        return ok(data={"name": name, "docstatus": 1}, message=_("Already confirmed"))

    doc.submit()
    return ok(
        data={
            "name": doc.name,
            "docstatus": doc.docstatus,
            "booking_status": doc.booking_status,
            "payment_plan": payment_plan_rows(name),
        },
        message=_("Booking {0} confirmed").format(name),
    )


@frappe.whitelist()
def cancel_booking(name, reason=None):
    """Cancelling puts the unit back on the market."""
    doc = base.read_doc("Property Booking", name)
    doc.check_permission("cancel")

    doc.cancel()
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(
        data={"name": name, "docstatus": doc.docstatus, "booking_status": doc.booking_status},
        message=_("Booking cancelled"),
    )


@frappe.whitelist()
def payment_plan(booking):
    base.read_doc("Property Booking", booking).check_permission("read")
    return ok(data={"rows": payment_plan_rows(booking), "collections": collections_for(booking)})


def payment_plan_rows(booking):
    if not base.can_read("Payment Plan"):
        return []

    rows = frappe.get_list(
        "Payment Plan",
        filters={"booking": booking},
        fields=[
            "name",
            "milestone",
            "due_date",
            "amount",
            "invoice",
            "payment_status",
            "late_fee_applied",
            "late_fee_amount",
        ],
        order_by="due_date asc",
    )

    invoices = [row.invoice for row in rows if row.invoice]
    outstanding = {}
    if invoices and base.can_read("Sales Invoice"):
        for invoice in frappe.get_list(
            "Sales Invoice",
            filters={"name": ["in", invoices]},
            fields=["name", "grand_total", "outstanding_amount", "status", "due_date"],
        ):
            outstanding[invoice.name] = invoice

    for row in rows:
        invoice = outstanding.get(row.invoice) or {}
        row["invoice_status"] = invoice.get("status")
        row["outstanding_amount"] = flt(invoice.get("outstanding_amount"), 2)
        row["paid_amount"] = flt(flt(invoice.get("grand_total")) - flt(invoice.get("outstanding_amount")), 2)

    return base.serialize(rows)


def collections_for(booking):
    """Billed / collected / outstanding for one booking."""
    if not (base.can_read("Payment Plan") and base.can_read("Sales Invoice")):
        return {"billed": 0.0, "collected": 0.0, "outstanding": 0.0, "invoices": 0}

    invoices = frappe.get_list("Payment Plan", filters={"booking": booking}, pluck="invoice")
    invoices = [i for i in invoices if i]
    if not invoices:
        return {"billed": 0.0, "collected": 0.0, "outstanding": 0.0, "invoices": 0}

    rows = frappe.get_list(
        "Sales Invoice",
        filters={"name": ["in", invoices], "docstatus": 1},
        fields=["sum(grand_total) as billed", "sum(outstanding_amount) as outstanding", "count(name) as invoices"],
    )
    row = rows[0] if rows else {}
    billed = flt(row.get("billed"))
    outstanding = flt(row.get("outstanding"))
    return {
        "billed": flt(billed, 2),
        "collected": flt(billed - outstanding, 2),
        "outstanding": flt(outstanding, 2),
        "invoices": row.get("invoices") or 0,
    }
