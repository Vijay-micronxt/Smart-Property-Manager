"""Lead — the top of the funnel.

The whole enquiry lifecycle the floor works: capture, qualify, follow up,
convert to an opportunity, and finally to a customer. Row-level visibility is
Frappe's job here (see ``crm.scope``), so a sales executive calling
``get_leads`` gets their own rows and nothing else.
"""

import frappe
from frappe import _


from property_core.api.crm import base
from property_core.api.utils import ok

LIST_FIELDS = [
    "name",
    "lead_name",
    "company_name",
    "email_id",
    "mobile_no",
    "phone",
    "status",
    "custom_lead_status",
    "custom_lead_source",
    "source",
    "custom_property",
    "custom_property_unit",
    "custom_unit_type",
    "custom_budget",
    "custom_required_area",
    "custom_next_follow_up_date",
    "custom_follow_up_owner",
    "lead_owner",
    "territory",
    "city",
    "owner",
    "creation",
    "modified",
]

SEARCH_FIELDS = ["lead_name", "mobile_no", "email_id", "company_name", "name"]

WRITABLE = {
    "lead_name",
    "first_name",
    "last_name",
    "salutation",
    "company_name",
    "email_id",
    "mobile_no",
    "phone",
    "whatsapp_no",
    "gender",
    "source",
    "custom_lead_status",
    "custom_lead_source",
    "custom_unit_type",
    "custom_required_area",
    "custom_budget",
    "custom_preferred_facing",
    "custom_property",
    "custom_property_unit",
    "custom_next_follow_up_date",
    "custom_follow_up_owner",
    "custom_follow_up_notes",
    "custom_disable_follow_up_reminders",
    "custom_address_line1",
    "custom_address_line2",
    "custom_pincode",
    "lead_owner",
    "territory",
    "city",
    "state",
    "country",
    "type",
    "request_type",
}


@frappe.whitelist()
def get_leads(
    search=None,
    status=None,
    source=None,
    owner=None,
    property=None,
    project=None,
    unit_type=None,
    from_date=None,
    to_date=None,
    mine=None,
    filters=None,
    order_by=None,
    page=1,
    page_size=20,
):
    """The lead list, filtered the way the screens filter it."""
    user = base.require_user()

    conditions = []
    if status:
        statuses = base.parse(status, default=status)
        conditions.append(["custom_lead_status", "in", statuses if isinstance(statuses, list) else [statuses]])
    if source:
        conditions.append(["custom_lead_source", "=", source])
    if owner:
        conditions.append(["lead_owner", "=", owner])
    if base.as_bool(mine):
        conditions.append(["lead_owner", "=", user])
    if property:
        conditions.append(["custom_property", "=", property])
    if unit_type:
        conditions.append(["custom_unit_type", "=", unit_type])
    if project:
        conditions.append(["custom_property", "in", _properties_of(project)])
    base.date_range(conditions, "creation", from_date, to_date)

    result = base.listing(
        "Lead",
        LIST_FIELDS,
        filters=filters,
        extra_filters=conditions,
        search=search,
        search_fields=SEARCH_FIELDS,
        order_by=order_by or "modified desc",
        page=page,
        page_size=page_size,
    )

    owners = base.user_names([row.get("lead_owner") for row in result["rows"]])
    assigned = base.assignments("Lead", [row["name"] for row in result["rows"]])
    for row in result["rows"]:
        row["lead_owner_name"] = owners.get(row.get("lead_owner"))
        row["assigned_to"] = assigned.get(row["name"], [])

    return ok(data=result)


@frappe.whitelist()
def get_lead(name):
    """One lead with everything hanging off it -- the detail screen in a single
    round trip."""
    doc = base.read_doc("Lead", name)
    payload = base.doc_payload(doc)

    payload["follow_ups"] = _follow_ups("Lead", name)
    payload["opportunities"] = base.serialize(
        frappe.get_list(
            "Opportunity",
            filters={"party_name": name, "opportunity_from": "Lead"},
            fields=[
                "name",
                "status",
                "opportunity_amount",
                "custom_property",
                "custom_property_unit",
                "custom_project",
                "transaction_date",
            ],
            order_by="creation desc",
        )
    )
    payload["bookings"] = base.serialize(
        frappe.get_list(
            "Property Booking",
            filters={"lead": name},
            fields=["name", "booking_status", "property_unit", "total_price", "booking_date", "docstatus"],
            order_by="creation desc",
        )
    )
    payload["customer"] = frappe.db.get_value("Customer", {"lead_name": name}, "name")
    payload["assigned_to"] = base.assignments("Lead", [name]).get(name, [])
    payload["activity"] = _activity("Lead", name)
    return ok(data=payload)


@frappe.whitelist()
def create_lead(data=None, **kwargs):
    """A new enquiry. ``lead_owner`` defaults to whoever is calling, which is
    also what decides who can see it afterwards."""
    user = base.require_user()
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})

    if not payload.get("lead_name") and not payload.get("first_name"):
        frappe.throw(_("Lead name is required"))

    doc = base.create_doc(
        "Lead",
        payload,
        WRITABLE,
        defaults={"lead_owner": payload.get("lead_owner") or user},
    )
    return ok(data=base.doc_payload(doc), message=_("Lead {0} created").format(doc.name))


@frappe.whitelist()
def update_lead(name, data=None, **kwargs):
    payload = base.parse(data, default={}) or {}
    payload.update({k: v for k, v in kwargs.items() if k in WRITABLE})

    doc, changed = base.write_doc("Lead", name, payload, WRITABLE)
    return ok(data=base.doc_payload(doc), message=_("Updated {0}").format(", ".join(changed) or "nothing"))


@frappe.whitelist()
def set_status(name, status, notes=None):
    """Move a lead along the pipeline. The native ``status`` follows through
    STATUS_MAP, so ERPNext's own reports stay honest."""
    doc = base.read_doc("Lead", name)
    doc.check_permission("write")

    doc.custom_lead_status = status
    if notes:
        doc.custom_follow_up_notes = notes
    doc.save()

    return ok(
        data={"name": doc.name, "custom_lead_status": doc.custom_lead_status, "status": doc.status},
        message=_("Lead marked {0}").format(status),
    )


@frappe.whitelist()
def assign_lead(name, user, note=None):
    """Hand the lead to someone. Both the follow-up owner and the ToDo move,
    because the desk shows one and the reminders read the other."""
    doc = base.read_doc("Lead", name)
    doc.check_permission("write")

    doc.custom_follow_up_owner = user
    if not doc.lead_owner:
        doc.lead_owner = user
    doc.save()

    base.assign_to("Lead", name, user, note or _("Lead assigned"))
    return ok(data={"name": name, "assigned_to": user}, message=_("Assigned to {0}").format(user))


@frappe.whitelist()
def transfer_ownership(name, user):
    """Give the lead away outright -- owner, follow-up owner and assignment."""
    doc = base.read_doc("Lead", name)
    doc.check_permission("write")

    doc.lead_owner = user
    doc.custom_follow_up_owner = user
    doc.save()
    base.assign_to("Lead", name, user, _("Lead transferred"))
    return ok(data={"name": name, "lead_owner": user})


@frappe.whitelist()
def convert_to_opportunity(
    name,
    property=None,
    property_unit=None,
    opportunity_amount=None,
    expected_closing=None,
    contact_date=None,
    notes=None,
):
    """Lead → Opportunity, with the property tagged on the way through.

    ERPNext's own mapper is used so nothing about the native funnel breaks;
    the property fields are ours and are filled here because an opportunity
    without a property cannot be worked (the field is mandatory) and the
    frontend should not have to make a second call to set it.
    """
    from erpnext.crm.doctype.lead.lead import make_opportunity

    lead = base.read_doc("Lead", name)
    lead.check_permission("read")

    existing = frappe.db.get_value(
        "Opportunity", {"party_name": name, "opportunity_from": "Lead", "status": ["!=", "Lost"]}, "name"
    )
    if existing:
        return ok(
            data={"name": existing, "already_existed": True},
            message=_("Opportunity {0} already exists for this lead").format(existing),
        )

    opportunity = make_opportunity(name)

    if property_unit and not property:
        property = frappe.db.get_value("Property Unit", property_unit, "property")
    opportunity.custom_property = property or lead.get("custom_property")
    opportunity.custom_property_unit = property_unit or lead.get("custom_property_unit")

    if not opportunity.custom_property:
        frappe.throw(_("Pick a property — an opportunity cannot be worked without one."))

    if opportunity_amount:
        opportunity.opportunity_amount = opportunity_amount
    elif opportunity.custom_property_unit:
        opportunity.opportunity_amount = frappe.db.get_value(
            "Property Unit", opportunity.custom_property_unit, "base_price"
        )
    if expected_closing:
        opportunity.expected_closing = expected_closing
    if contact_date:
        opportunity.contact_date = contact_date
    if notes:
        opportunity.custom_follow_up_notes = notes

    opportunity.insert()

    return ok(
        data=base.doc_payload(opportunity),
        message=_("Opportunity {0} created").format(opportunity.name),
    )


@frappe.whitelist()
def create_customer(name):
    """Lead → Customer. A booking needs one, and ERPNext's own conversion drops
    the address, so the app's version is used."""
    base.read_doc("Lead", name).check_permission("read")

    from property_core.property_core.crm.customer_from_lead import make_customer_from_lead

    customer = make_customer_from_lead(name)
    customer_name = customer if isinstance(customer, str) else getattr(customer, "name", customer)
    return ok(data={"customer": customer_name}, message=_("Customer {0} ready").format(customer_name))


@frappe.whitelist()
def find_duplicates(mobile_no, exclude=None):
    """Same number already in the system? Used by the capture form as you type."""
    base.require_user()
    from property_core.property_core.crm.lead_events import find_duplicates as _find

    return ok(data=base.serialize(_find(mobile_no, exclude)))


@frappe.whitelist()
def pipeline(from_date=None, to_date=None, project=None):
    """Lead counts per status -- the funnel chart, scoped to what the caller
    may see."""
    base.require_user()

    filters = []
    base.date_range(filters, "creation", from_date, to_date)
    if project:
        filters.append(["custom_property", "in", _properties_of(project)])

    rows = frappe.get_list(
        "Lead",
        filters=filters,
        fields=["custom_lead_status as status", "count(name) as total"],
        group_by="custom_lead_status",
        order_by="total desc",
    )
    return ok(data={"total": sum(row.total for row in rows), "by_status": rows})


# --------------------------------------------------------------------------- #

def _properties_of(project):
    return frappe.get_list("Property", filters={"project": project}, pluck="name") or [""]


def _follow_ups(doctype, name, limit=20):
    return base.serialize(
        frappe.get_list(
            "Property Follow Up",
            filters={"reference_doctype": doctype, "reference_name": name},
            fields=[
                "name",
                "follow_up_type",
                "status",
                "scheduled_on",
                "assigned_to",
                "outcome",
                "notes",
                "next_follow_up_on",
                "completed_on",
            ],
            order_by="scheduled_on desc",
            limit=limit,
        )
    )


def _activity(doctype, name, limit=20):
    """Calls, WhatsApp and emails logged against the record."""
    rows = frappe.get_list(
        "Communication",
        filters={"reference_doctype": doctype, "reference_name": name},
        fields=["name", "communication_type", "communication_medium", "subject", "sent_or_received", "creation"],
        order_by="creation desc",
        limit=limit,
        ignore_permissions=True,
    )
    return base.serialize(rows)
