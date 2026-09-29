"""After the sale: handing the unit over (Property Allocation) and the
paperwork behind it (Property Agreement).

    Property Booking (confirmed)
        -> Property Agreement   sale / lease agreement, signed date, deposit
        -> Property Allocation  submitted = unit becomes Allocated (sale) or
                                Leased (lease/rental), agreement goes Active

``create_from_booking`` builds both from a confirmed booking in one call,
which is what the desk does by hand in three screens.
"""

import frappe
from frappe import _
from frappe.utils import today

from property_core.api.crm import base
from property_core.api.utils import ok

ALLOCATION_FIELDS = [
    "name",
    "customer",
    "property_unit",
    "project",
    "allocation_type",
    "status",
    "start_date",
    "end_date",
    "booking",
    "agreement",
    "rent_amount",
    "billing_frequency",
    "next_billing_date",
    "docstatus",
    "modified",
]

ALLOCATION_WRITABLE = {
    "customer",
    "property_unit",
    "project",
    "allocation_type",
    "start_date",
    "end_date",
    "booking",
    "agreement",
    "rent_amount",
    "billing_frequency",
    "billing_day",
}

AGREEMENT_FIELDS = [
    "name",
    "agreement_type",
    "customer",
    "property_unit",
    "project",
    "agreement_status",
    "start_date",
    "end_date",
    "signed_date",
    "security_deposit_amount",
    "security_deposit_received",
    "document_attachment",
    "modified",
]

AGREEMENT_WRITABLE = {
    "agreement_type",
    "customer",
    "property_unit",
    "project",
    "agreement_status",
    "start_date",
    "end_date",
    "signed_date",
    "security_deposit_amount",
    "document_attachment",
}


# --------------------------------------------------------------------------- #
# allocations
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_allocations(
    customer=None, property_unit=None, booking=None, status=None, allocation_type=None, search=None, page=1, page_size=20
):
    base.require_user()
    conditions = [["docstatus", "<", 2]]
    for field, value in (
        ("customer", customer),
        ("property_unit", property_unit),
        ("booking", booking),
        ("status", status),
        ("allocation_type", allocation_type),
    ):
        if value:
            conditions.append([field, "=", value])
    return ok(
        data=base.listing(
            "Property Allocation",
            ALLOCATION_FIELDS,
            extra_filters=conditions,
            search=search,
            search_fields=["name", "customer", "property_unit"],
            order_by="start_date desc",
            page=page,
            page_size=page_size,
        )
    )


@frappe.whitelist()
def get_allocation(name):
    return ok(data=base.doc_payload(base.read_doc("Property Allocation", name)))


@frappe.whitelist()
def create_allocation(data=None, submit=0, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in ALLOCATION_WRITABLE})
    doc = base.create_doc(
        "Property Allocation", payload, ALLOCATION_WRITABLE, defaults={"allocation_type": "Sale", "start_date": today()}
    )
    if base.as_bool(submit):
        doc.submit()
    return ok(data=base.doc_payload(doc), message=_("Allocation {0} created").format(doc.name))


@frappe.whitelist()
def update_allocation(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in ALLOCATION_WRITABLE})
    doc, changed = base.write_doc("Property Allocation", name, payload, ALLOCATION_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def submit_allocation(name):
    """Hand the unit over: it becomes Allocated (sale) or Leased."""
    doc = base.read_doc("Property Allocation", name)
    doc.check_permission("submit")
    if doc.docstatus == 0:
        doc.submit()
    return ok(data=base.doc_payload(doc), message=_("Allocation {0} active").format(name))


@frappe.whitelist()
def cancel_allocation(name, reason=None):
    """Terminate: the unit goes back to Available."""
    doc = base.read_doc("Property Allocation", name)
    doc.check_permission("cancel")
    doc.cancel()
    if reason:
        doc.add_comment("Comment", text=reason)
    return ok(data={"name": name, "docstatus": doc.docstatus, "status": "Terminated"}, message=_("Allocation terminated"))


@frappe.whitelist()
def renew_lease(name, new_end_date, escalation_percent=0):
    from property_core.property_core.doctype.property_allocation.property_allocation import renew_lease as _renew

    base.read_doc("Property Allocation", name).check_permission("write")
    return ok(data=_renew(name, new_end_date, escalation_percent), message=_("Lease renewed"))


@frappe.whitelist()
def create_from_booking(
    booking, allocation_type="Sale", start_date=None, signed_date=None, with_agreement=1, submit=1, security_deposit_amount=0
):
    """Confirmed booking -> agreement + allocation, in one step. Idempotent:
    an existing live allocation for the booking is returned as is."""
    b = base.read_doc("Property Booking", booking)
    if b.docstatus != 1:
        frappe.throw(_("Confirm (submit) booking {0} first").format(booking))

    existing = frappe.db.get_value("Property Allocation", {"booking": booking, "docstatus": ["<", 2]}, "name")
    if existing:
        return ok(data=base.doc_payload(frappe.get_doc("Property Allocation", existing)), message=_("Already allocated"))

    start = start_date or today()
    agreement = None
    if base.as_bool(with_agreement, True):
        agreement = base.create_doc(
            "Property Agreement",
            {
                "agreement_type": "Sale Agreement" if allocation_type == "Sale" else "Lease Agreement",
                "customer": b.customer,
                "property_unit": b.property_unit,
                "project": b.project,
                "start_date": start,
                "signed_date": signed_date,
                "security_deposit_amount": security_deposit_amount,
            },
            AGREEMENT_WRITABLE,
        ).name

    doc = base.create_doc(
        "Property Allocation",
        {
            "customer": b.customer,
            "property_unit": b.property_unit,
            "project": b.project,
            "allocation_type": allocation_type,
            "start_date": start,
            "booking": booking,
            "agreement": agreement,
        },
        ALLOCATION_WRITABLE,
    )
    if base.as_bool(submit, True):
        doc.submit()
    return ok(
        data={**base.doc_payload(doc), "agreement": agreement},
        message=_("Unit {0} allocated to {1}").format(b.property_unit, b.customer),
    )


# --------------------------------------------------------------------------- #
# agreements
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def get_agreements(customer=None, property_unit=None, status=None, agreement_type=None, search=None, page=1, page_size=20):
    base.require_user()
    conditions = []
    for field, value in (
        ("customer", customer),
        ("property_unit", property_unit),
        ("agreement_status", status),
        ("agreement_type", agreement_type),
    ):
        if value:
            conditions.append([field, "=", value])
    return ok(
        data=base.listing(
            "Property Agreement",
            AGREEMENT_FIELDS,
            extra_filters=conditions,
            search=search,
            search_fields=["name", "customer", "property_unit"],
            order_by="start_date desc",
            page=page,
            page_size=page_size,
        )
    )


@frappe.whitelist()
def get_agreement(name):
    return ok(data=base.doc_payload(base.read_doc("Property Agreement", name)))


@frappe.whitelist()
def create_agreement(data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in AGREEMENT_WRITABLE})
    doc = base.create_doc("Property Agreement", payload, AGREEMENT_WRITABLE, defaults={"start_date": today()})
    return ok(data=base.doc_payload(doc), message=_("Agreement {0} created").format(doc.name))


@frappe.whitelist()
def update_agreement(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in AGREEMENT_WRITABLE})
    doc, changed = base.write_doc("Property Agreement", name, payload, AGREEMENT_WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def record_security_deposit(name):
    """Book the deposit (Journal Entry to the Security Deposit account in
    Property Core Settings)."""
    from property_core.property_core.doctype.property_agreement.property_agreement import (
        record_security_deposit as _record,
    )

    base.read_doc("Property Agreement", name).check_permission("write")
    return ok(data={"journal_entry": _record(name)}, message=_("Deposit recorded"))


@frappe.whitelist()
def refund_security_deposit(name):
    from property_core.property_core.doctype.property_agreement.property_agreement import (
        refund_security_deposit as _refund,
    )

    base.read_doc("Property Agreement", name).check_permission("write")
    return ok(data={"journal_entry": _refund(name)}, message=_("Deposit refunded"))
