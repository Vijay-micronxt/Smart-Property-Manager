"""One follow-up record, usable anywhere in the funnel.

JD ran follow-ups as CRM Task rows hanging off CRM Lead, which meant the
history died the moment a lead became an Opportunity or a Booking. This is a
Dynamic Link instead, so the same call/site-visit/WhatsApp trail follows the
customer from first enquiry through to possession.

Closing a follow-up writes the next date back onto the Lead or Opportunity,
which is what notifications/lead_followup.py reads when it sends reminders.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime

# reference_doctype -> (name field, phone field, property field, unit field, status field)
REFERENCE_MAP = {
    "Lead": ("lead_name", "mobile_no", "custom_property", "custom_property_unit", "custom_lead_status"),
    # Opportunity's property fields are custom_* -- renamed so ERPNext's
    # Lead -> Opportunity mapper copies them across by itself. Reading the old
    # names here threw "Unknown column 'property'" on every follow-up logged
    # against an opportunity.
    "Opportunity": ("party_name", "contact_mobile", "custom_property", "custom_property_unit", "status"),
    "Property Booking": ("customer", None, "unit_property", "property_unit", "booking_status"),
    "Property Unit": ("unit_number", None, "property", "name", "availability_status"),
    "Customer": ("customer_name", "mobile_no", None, None, None),
}

OPEN_STATUSES = ("Open", "Rescheduled")


class PropertyFollowUp(Document):
    def validate(self):
        self.pull_reference_details()
        self.set_completion_stamp()

    def on_update(self):
        self.sync_todo()
        self.push_next_follow_up()

    def on_trash(self):
        _close_todos(self.doctype, self.name)

    # ------------------------------------------------------------------ #

    def pull_reference_details(self):
        mapping = REFERENCE_MAP.get(self.reference_doctype)
        if not mapping:
            return

        name_field, phone_field, property_field, unit_field, status_field = mapping
        fields = [f for f in mapping if f]
        values = frappe.db.get_value(self.reference_doctype, self.reference_name, fields, as_dict=True)
        if not values:
            return

        self.party_name = values.get(name_field) or self.reference_name
        if phone_field and not self.contact_number:
            self.contact_number = values.get(phone_field)
        if property_field and not self.property:
            self.property = values.get(property_field)
        if unit_field and not self.property_unit:
            self.property_unit = values.get(unit_field)
        if status_field:
            self.lead_status_at_follow_up = values.get(status_field)

    def set_completion_stamp(self):
        if self.status == "Completed":
            if not self.completed_on:
                self.completed_on = now_datetime()
            if not self.completed_by:
                self.completed_by = frappe.session.user
        else:
            self.completed_on = None
            self.completed_by = None

    def sync_todo(self):
        """Open follow-ups show up in the assignee's ToDo list; closed ones leave."""
        if self.status not in OPEN_STATUSES:
            _close_todos(self.doctype, self.name)
            return

        existing = frappe.db.exists(
            "ToDo",
            {
                "reference_type": self.doctype,
                "reference_name": self.name,
                "allocated_to": self.assigned_to,
                "status": "Open",
            },
        )
        if existing:
            frappe.db.set_value("ToDo", existing, "date", getdate(self.scheduled_on))
            return

        _close_todos(self.doctype, self.name)
        frappe.get_doc(
            {
                "doctype": "ToDo",
                "allocated_to": self.assigned_to,
                "reference_type": self.doctype,
                "reference_name": self.name,
                "date": getdate(self.scheduled_on),
                "priority": "Medium",
                "description": f"{self.follow_up_type} follow-up: {self.party_name or self.reference_name}",
            }
        ).insert(ignore_permissions=True)

    def push_next_follow_up(self):
        """Keep the source document's reminder date in step with the latest plan."""
        if not self.next_follow_up_on or self.reference_doctype not in ("Lead", "Opportunity"):
            return

        next_date = getdate(self.next_follow_up_on)
        if self.reference_doctype == "Lead":
            frappe.db.set_value(
                "Lead",
                self.reference_name,
                {
                    "custom_next_follow_up_date": next_date,
                    "custom_follow_up_owner": self.assigned_to,
                },
                update_modified=False,
            )
        else:
            frappe.db.set_value(
                "Opportunity", self.reference_name, "contact_date", next_date, update_modified=False
            )


def _close_todos(reference_type, reference_name):
    for todo in frappe.get_all(
        "ToDo",
        filters={"reference_type": reference_type, "reference_name": reference_name, "status": "Open"},
        pluck="name",
    ):
        frappe.db.set_value("ToDo", todo, "status", "Closed", update_modified=False)


# ---------------------------------------------------------------------- #
# APIs used by the Lead / Opportunity / Booking forms
# ---------------------------------------------------------------------- #


@frappe.whitelist()
def get_follow_up_history(reference_doctype, reference_name, start=0, page_length=20):
    """Paginated trail for the Follow Ups tab. Replaces JD's get_task_history."""
    start, page_length = int(start), int(page_length)

    filters = {"reference_doctype": reference_doctype, "reference_name": reference_name}
    total = frappe.db.count("Property Follow Up", filters)

    rows = frappe.get_all(
        "Property Follow Up",
        filters=filters,
        fields=[
            "name",
            "follow_up_type",
            "status",
            "scheduled_on",
            "assigned_to",
            "outcome",
            "notes",
            "next_follow_up_on",
            "next_action",
            "completed_on",
            "owner",
            "lead_status_at_follow_up",
        ],
        order_by="scheduled_on desc",
        limit_start=start,
        limit_page_length=page_length,
    )

    user_names = {}
    for row in rows:
        for key in ("assigned_to", "owner"):
            user = row.get(key)
            if user and user not in user_names:
                user_names[user] = frappe.db.get_value("User", user, "full_name") or user
        row["assigned_to_name"] = user_names.get(row.assigned_to, row.assigned_to)
        row["owner_name"] = user_names.get(row.owner, row.owner)

    return {
        "rows": rows,
        "total": total,
        "loaded": start + len(rows),
        "has_more": (start + len(rows)) < total,
    }


@frappe.whitelist()
def log_follow_up(
    reference_doctype,
    reference_name,
    follow_up_type="Call",
    outcome=None,
    notes=None,
    next_follow_up_on=None,
    next_action=None,
    scheduled_on=None,
    assigned_to=None,
    status="Completed",
):
    """One-call entry point for the "Log Follow Up" dialog on Lead/Opportunity."""
    doc = frappe.new_doc("Property Follow Up")
    doc.update(
        {
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "follow_up_type": follow_up_type,
            "status": status,
            "scheduled_on": get_datetime(scheduled_on) if scheduled_on else now_datetime(),
            "assigned_to": assigned_to or frappe.session.user,
            "outcome": outcome,
            "notes": notes,
            "next_follow_up_on": get_datetime(next_follow_up_on) if next_follow_up_on else None,
            "next_action": next_action,
        }
    )
    doc.insert()
    return doc.name


@frappe.whitelist()
def get_open_follow_up(reference_doctype, reference_name):
    rows = frappe.get_all(
        "Property Follow Up",
        filters={
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "status": ["in", OPEN_STATUSES],
        },
        fields=["name", "scheduled_on", "follow_up_type", "assigned_to"],
        order_by="scheduled_on asc",
        limit=1,
    )
    return rows[0] if rows else None
