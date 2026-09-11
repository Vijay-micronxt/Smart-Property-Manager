"""Inbound calls become leads, ported from JD's "Call Log to CRM Lead".

For a real-estate desk a missed call is a lead, so nothing that rings should
fall on the floor. Two things changed in the port:

  * the call is attached to the Lead through Call Log's own ``links`` table,
    so it shows on the Lead timeline instead of only as a comment
  * a repeat caller gets a Property Follow Up row rather than a comment, which
    is what the Follow Ups tab and the reminder engine read
"""

import frappe
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.utils import now_datetime

CALL_SOURCE = "Exotel Call"
FALLBACK_ROLE = "Sales Manager"


def after_insert(doc, method=None):
    if doc.get("type") == "Outgoing":
        return

    number = _last_ten(doc.get("from"))
    if not number:
        return

    lead = _find_lead(number)
    if lead:
        _log_repeat_call(doc, lead)
    else:
        lead = _create_lead(doc, number)

    if lead:
        _link_call_to_lead(doc, lead)


def _last_ten(raw):
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else None


def _find_lead(number):
    return frappe.db.get_value("Lead", {"mobile_no": ["like", f"%{number}"]}, "name")


def _create_lead(call, number):
    source = CALL_SOURCE if frappe.db.exists("Lead Source", CALL_SOURCE) else None

    lead = frappe.get_doc(
        {
            "doctype": "Lead",
            "first_name": "Unknown Caller",
            "mobile_no": number,
            "source": source,
            "custom_lead_source": CALL_SOURCE,
            "custom_lead_status": "New",
        }
    )
    lead.insert(ignore_permissions=True)

    owner = _assignee(call)
    if owner:
        frappe.db.set_value(
            "Lead",
            lead.name,
            {"lead_owner": owner, "custom_follow_up_owner": owner},
            update_modified=False,
        )

    _create_follow_up(call, lead.name, owner, "Missed/inbound call — no existing lead.")
    return lead.name


def _log_repeat_call(call, lead):
    owner = frappe.db.get_value("Lead", lead, "custom_follow_up_owner") or _assignee(call)
    _create_follow_up(call, lead, owner, f"Repeat call from {call.get('from')}.")


def _create_follow_up(call, lead, owner, note):
    try:
        frappe.get_doc(
            {
                "doctype": "Property Follow Up",
                "reference_doctype": "Lead",
                "reference_name": lead,
                "follow_up_type": "Call",
                "status": "Open",
                "scheduled_on": call.get("start_time") or now_datetime(),
                "assigned_to": owner or frappe.session.user,
                "notes": note,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Call Log follow-up: {call.name}")


def _link_call_to_lead(call, lead):
    # Creating the Lead also creates a Contact, whose on_update links itself
    # back onto this very Call Log -- so the copy we were handed is already
    # stale by the time we get here.
    try:
        call.reload()
    except Exception:
        return

    already = any(
        row.link_doctype == "Lead" and row.link_name == lead for row in call.get("links") or []
    )
    if already:
        return

    try:
        call.append("links", {"link_doctype": "Lead", "link_name": lead})
        call.save(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Call Log link: {call.name}")


def _assignee(call):
    """Whoever picked up, else the agent the call was routed to, else anyone
    holding the fallback role. JD assigned every new call-lead to all Super
    Admins, which buried the real owner."""
    if call.get("employee_user_id"):
        return call.employee_user_id

    agent = _last_ten(call.get("to"))
    if agent:
        user = frappe.db.get_value("User", {"mobile_no": ["like", f"%{agent}"], "enabled": 1}, "name")
        if user:
            return user

    holders = frappe.get_all(
        "Has Role", filters={"role": FALLBACK_ROLE, "parenttype": "User"}, pluck="parent", limit=1
    )
    return holders[0] if holders else None


def keep_single_assignment(doc, method=None):
    """JD's "remove old assignment with new one": a lead reassigned five times
    kept five open ToDos, so five people thought it was theirs."""
    if doc.is_new():
        return

    todos = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "status": ["not in", ["Cancelled", "Closed"]],
        },
        fields=["name", "allocated_to"],
        order_by="creation desc",
    )
    if len(todos) < 2:
        return

    keep = next((t for t in todos if t.allocated_to == doc.get("lead_owner")), todos[0])

    for todo in todos:
        if todo.name == keep.name:
            continue
        try:
            remove_assignment(doc.doctype, doc.name, todo.allocated_to)
        except Exception:
            frappe.db.set_value("ToDo", todo.name, "status", "Closed", update_modified=False)
