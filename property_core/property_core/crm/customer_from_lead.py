"""Make a Lead enough to become a Customer, from anywhere in the funnel.

Two gaps this closes.

A lead had a mobile number and nowhere to put an address, so the Customer that
came out of it had no address either and somebody retyped it later. The fields
here are all optional -- a walk-in enquiry that leaves a number and nothing
else still saves.

And ERPNext's own Lead -> Customer mapper never carries the address across:
`_set_missing_values` attaches the Address and Contact, but only
`make_opportunity` and `make_quotation` call it, never `_make_customer`. So the
link is made here instead, on the Customer itself, which means it happens no
matter which button created it -- Lead, Opportunity or Property Booking.
"""

import frappe

ADDRESS_FIELDS = [
    {
        "fieldname": "custom_address_line1",
        "fieldtype": "Data",
        "label": "Address Line 1",
        "insert_after": "column_break_38",
        "description": "Optional. Filled in here, it follows the lead into the Customer.",
    },
    {
        "fieldname": "custom_address_line2",
        "fieldtype": "Data",
        "label": "Address Line 2",
        "insert_after": "custom_address_line1",
    },
    {
        "fieldname": "custom_pincode",
        "fieldtype": "Data",
        "label": "Pincode",
        "insert_after": "country",
    },
]


def sync_address_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields({"Lead": ADDRESS_FIELDS}, ignore_validate=True, update=True)


def delete_address_fields():
    frappe.db.delete(
        "Custom Field",
        {"dt": "Lead", "fieldname": ["in", [f["fieldname"] for f in ADDRESS_FIELDS]]},
    )


# ---------------------------------------------------------------------- #
# Lead -> Address
# ---------------------------------------------------------------------- #


def sync_lead_address(doc, method=None):
    """Keep a real Address record in step with what was typed on the Lead.

    Address needs line 1, city and country to save, so anything less is simply
    not an address yet and is left alone -- these fields are optional.
    """
    if not (doc.get("custom_address_line1") and doc.get("city") and doc.get("country")):
        return

    existing = _lead_address(doc.name)

    values = {
        "address_line1": doc.custom_address_line1,
        "address_line2": doc.get("custom_address_line2"),
        "city": doc.city,
        "state": doc.get("state"),
        "country": doc.country,
        "pincode": doc.get("custom_pincode"),
        "phone": doc.get("mobile_no"),
        "email_id": doc.get("email_id"),
    }

    try:
        if existing:
            address = frappe.get_doc("Address", existing)
            address.update(values)
            address.flags.ignore_permissions = True
            address.save()
            return

        address = frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": doc.lead_name or doc.name,
                "address_type": "Billing",
                "is_primary_address": 1,
                **values,
                "links": [{"link_doctype": "Lead", "link_name": doc.name}],
            }
        )
        address.flags.ignore_permissions = True
        address.insert()
    except Exception:
        # An address that will not save must never block saving the lead.
        frappe.log_error(frappe.get_traceback(), f"Lead Address Sync: {doc.name}")


def _lead_address(lead):
    rows = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Lead", "link_name": lead, "parenttype": "Address"},
        pluck="parent",
        limit=1,
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------- #
# Lead -> Customer
# ---------------------------------------------------------------------- #


def link_lead_records(doc, method=None):
    """Carry the lead's Address and Contact onto the Customer made from it."""
    lead = doc.get("lead_name")
    if not lead or not frappe.db.exists("Lead", lead):
        return

    for parenttype in ("Address", "Contact"):
        for parent in frappe.get_all(
            "Dynamic Link",
            filters={"link_doctype": "Lead", "link_name": lead, "parenttype": parenttype},
            pluck="parent",
        ):
            _attach(parenttype, parent, doc.name)

    address = _lead_address(lead)
    if address and not doc.get("customer_primary_address"):
        frappe.db.set_value(
            "Customer", doc.name, "customer_primary_address", address, update_modified=False
        )


def _attach(parenttype, parent, customer):
    already = frappe.db.exists(
        "Dynamic Link",
        {
            "parenttype": parenttype,
            "parent": parent,
            "link_doctype": "Customer",
            "link_name": customer,
        },
    )
    if already:
        return

    try:
        record = frappe.get_doc(parenttype, parent)
        record.append("links", {"link_doctype": "Customer", "link_name": customer})
        record.flags.ignore_permissions = True
        record.save()
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Lead {parenttype} -> Customer {customer}")


@frappe.whitelist()
def make_customer_from_lead(lead):
    """Create (or return) the Customer for a lead.

    Used by the Create > Customer button on Opportunity and Property Booking,
    so the same lead never spawns two customers.
    """
    frappe.has_permission("Lead", "read", doc=lead, throw=True)

    existing = frappe.db.get_value("Customer", {"lead_name": lead}, "name")
    if existing:
        return existing

    from erpnext.crm.doctype.lead.lead import _make_customer

    customer = _make_customer(lead, ignore_permissions=True)
    customer.flags.ignore_permissions = True
    customer.insert()
    return customer.name
