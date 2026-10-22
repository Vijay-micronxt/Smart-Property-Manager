"""Push notifications to the sales app.

Nothing here talks to Firebase. ``frappe_fcm_notification`` already pushes
every Notification Log to the user's registered devices (User Device rows),
so a push is simply a Notification Log for the right user with a subject and
a body. That also means the desk bell and the phone show the same thing.

What the app adds is *when* to write one:

* a follow-up assigned to someone else, or moved to a new person
* a follow-up coming up in the next few minutes (cron, every 5 minutes)
* a morning digest of today's and overdue follow-ups per user
* a Lead or Opportunity changing owner (transfer)

Assignments made through Frappe's assign-to (the API's assign endpoints, the
desk sidebar) already write their own Notification Log, so they push without
anything here.
"""

import frappe
from frappe import _
from frappe.utils import (
    add_to_date,
    cint,
    format_datetime,
    get_datetime,
    get_fullname,
    getdate,
    now_datetime,
    strip_html,
    today,
)

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)

OPEN_FOLLOW_UP = ("Open", "Rescheduled")
CLOSED_OPPORTUNITY = ("Lost", "Closed", "Converted")


def push_enabled():
    """On unless switched off; a site that has not migrated the new fields yet
    still pushes."""
    settings = get_settings()
    if not settings:
        return False
    return bool(cint(settings.get("enable_push_notifications", 1)))


def _setting(field, default):
    settings = get_settings()
    value = settings.get(field) if settings else None
    return default if value in (None, "") else value


def send(user, subject, body=None, document_type=None, document_name=None, from_user=None):
    """Write one Notification Log for ``user``. The FCM app picks it up on
    insert. Never raises -- a failed push must not roll back the save that
    caused it."""
    if not user or user in ("Guest", "Administrator"):
        return None
    from frappe.desk.doctype.notification_settings.notification_settings import is_notifications_enabled

    if not frappe.db.get_value("User", user, "enabled") or not is_notifications_enabled(user):
        return None

    try:
        log = frappe.get_doc(
            {
                "doctype": "Notification Log",
                "for_user": user,
                "from_user": from_user or frappe.session.user,
                "type": "Alert",
                "subject": subject,
                "email_content": body or subject,
                "document_type": document_type,
                "document_name": document_name,
            }
        )
        log.insert(ignore_permissions=True)
        return log.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Property Push Notification")
        return None


def fill_notification_body(doc, method=None):
    """Notification Log before_insert, for every log on the site.

    The FCM app strips HTML off ``email_content`` with a regex and dies on
    None, which is what Frappe writes for an assignment without a note and an
    unassignment. Falling back to the subject keeps those pushes alive.
    """
    if not strip_html(doc.get("email_content") or "").strip():
        doc.email_content = doc.subject


# --------------------------------------------------------------------------- #
# Property Follow Up
# --------------------------------------------------------------------------- #

def _party(doc):
    return doc.get("party_name") or doc.reference_name


def _when(value):
    return format_datetime(value, "dd MMM, hh:mm a") if value else ""


def on_follow_up_update(doc):
    """Called from PropertyFollowUp.on_update: tell the assignee about a
    follow-up somebody else put on their plate."""
    if not push_enabled() or doc.status not in OPEN_FOLLOW_UP or not doc.assigned_to:
        return
    before = doc.get_doc_before_save()  # None on insert
    if before and before.assigned_to == doc.assigned_to:
        return
    if doc.assigned_to == frappe.session.user:
        return

    send(
        doc.assigned_to,
        _("New follow-up: {0} with {1}").format(doc.follow_up_type or _("Follow-up"), _party(doc)),
        _("{0} assigned you a follow-up on {1} {2}, due {3}.").format(
            get_fullname(frappe.session.user),
            _(doc.reference_doctype),
            doc.reference_name,
            _when(doc.scheduled_on),
        ),
        doc.reference_doctype,
        doc.reference_name,
    )


def reset_reminder(doc):
    """Called from validate: a new time or a new person earns a new reminder."""
    if doc.is_new():
        return
    if doc.has_value_changed("scheduled_on") or doc.has_value_changed("assigned_to"):
        doc.reminder_sent_on = None


def send_due_reminders():
    """Cron, every 5 minutes: remind the assignee shortly before a follow-up.

    The window looks an hour back too, so a worker that was down for a bit
    still delivers late reminders instead of silently skipping them, but never
    replays the whole backlog.
    """
    if not push_enabled():
        return

    lead_minutes = cint(_setting("push_follow_up_before_minutes", 15)) or 15
    now = now_datetime()

    rows = frappe.get_all(
        "Property Follow Up",
        filters=[
            ["status", "in", OPEN_FOLLOW_UP],
            ["assigned_to", "is", "set"],
            ["reminder_sent_on", "is", "not set"],
            ["scheduled_on", "between", [add_to_date(now, hours=-1), add_to_date(now, minutes=lead_minutes)]],
        ],
        fields=[
            "name",
            "reference_doctype",
            "reference_name",
            "party_name",
            "follow_up_type",
            "scheduled_on",
            "assigned_to",
            "creation",
        ],
        limit=500,
    )

    for row in rows:
        # logged "now" -- the user is on the call already, nothing to remind
        if get_datetime(row.creation) >= add_to_date(get_datetime(row.scheduled_on), minutes=-1):
            frappe.db.set_value("Property Follow Up", row.name, "reminder_sent_on", now, update_modified=False)
            continue

        late = get_datetime(row.scheduled_on) < now
        subject = (
            _("Follow-up overdue: {0}") if late else _("Follow-up at {1}: {0}")
        ).format(_party(row), format_datetime(row.scheduled_on, "hh:mm a"))
        send(
            row.assigned_to,
            subject,
            _("{0} with {1} ({2} {3}), scheduled {4}.").format(
                row.follow_up_type or _("Follow-up"),
                _party(row),
                _(row.reference_doctype),
                row.reference_name,
                _when(row.scheduled_on),
            ),
            row.reference_doctype,
            row.reference_name,
            from_user="Administrator",
        )
        frappe.db.set_value("Property Follow Up", row.name, "reminder_sent_on", now, update_modified=False)

    frappe.db.commit()


def send_daily_digest():
    """Cron, every morning: one push per user with today's and overdue
    follow-ups.

    Counts open Property Follow Up rows, plus Leads and Opportunities that
    only carry a next follow-up date. A record that has both is counted once.
    """
    if not push_enabled() or not cint(_setting("push_daily_digest", 1)):
        return

    run_date = getdate(today())
    counts = {}  # user -> {"today": n, "overdue": n}
    seen = set()  # (doctype, name) already counted through a follow-up row

    def add(user, due, ref):
        if not user or ref in seen:
            return
        seen.add(ref)
        due = getdate(due)
        if due > run_date:
            return
        bucket = counts.setdefault(user, {"today": 0, "overdue": 0})
        bucket["today" if due == run_date else "overdue"] += 1

    for row in frappe.get_all(
        "Property Follow Up",
        filters={"status": ["in", OPEN_FOLLOW_UP], "scheduled_on": ["<", add_to_date(run_date, days=1)]},
        fields=["reference_doctype", "reference_name", "assigned_to", "scheduled_on"],
        order_by="scheduled_on desc",
        limit=20000,
    ):
        add(row.assigned_to, row.scheduled_on, (row.reference_doctype, row.reference_name))

    settings = get_settings()
    stop_statuses = settings.get_lead_stop_statuses() if settings else []
    lead_filters = {
        "custom_next_follow_up_date": ["<=", run_date],
        "custom_disable_follow_up_reminders": 0,
        "disabled": 0,
    }
    if stop_statuses:
        lead_filters["status"] = ["not in", stop_statuses]
    for row in frappe.get_all(
        "Lead",
        filters=lead_filters,
        fields=["name", "custom_next_follow_up_date", "custom_follow_up_owner", "lead_owner"],
        limit=20000,
    ):
        add(row.custom_follow_up_owner or row.lead_owner, row.custom_next_follow_up_date, ("Lead", row.name))

    if frappe.get_meta("Opportunity").has_field("custom_next_follow_up_date"):
        for row in frappe.get_all(
            "Opportunity",
            filters={
                "custom_next_follow_up_date": ["<", add_to_date(run_date, days=1)],
                "status": ["not in", CLOSED_OPPORTUNITY],
            },
            fields=["name", "custom_next_follow_up_date", "opportunity_owner"],
            limit=20000,
        ):
            add(row.opportunity_owner, row.custom_next_follow_up_date, ("Opportunity", row.name))

    for user, bucket in counts.items():
        if not (bucket["today"] or bucket["overdue"]):
            continue
        send(
            user,
            _("Today: {0} follow-ups, {1} overdue").format(bucket["today"], bucket["overdue"]),
            _("Open the app to see today's calls and visits."),
            "Property Follow Up",
            None,
            from_user="Administrator",
        )

    frappe.db.commit()


# --------------------------------------------------------------------------- #
# owner transfer
# --------------------------------------------------------------------------- #

OWNER_FIELD = {"Lead": "lead_owner", "Opportunity": "opportunity_owner"}


def on_owner_change(doc, method=None):
    """Lead / Opportunity on_update: when the owner moves, tell the new owner
    and the one who lost it.

    The API's assign/transfer endpoints set ``doc.flags.skip_owner_push``:
    they also reassign through Frappe, which already pushes to both sides.
    """
    field = OWNER_FIELD.get(doc.doctype)
    if not field or doc.flags.skip_owner_push or not push_enabled():
        return

    before = doc.get_doc_before_save()
    if not before:
        return
    old_owner, new_owner = before.get(field), doc.get(field)
    if not new_owner or old_owner == new_owner:
        return

    actor = frappe.session.user
    title = doc.get("lead_name") or doc.get("customer_name") or doc.get("party_name") or doc.name
    label = _(doc.doctype)

    if new_owner != actor:
        send(
            new_owner,
            _("{0} transferred to you: {1}").format(label, title),
            _("{0} gave you {1} {2}.").format(get_fullname(actor), label, doc.name),
            doc.doctype,
            doc.name,
        )
    if old_owner and old_owner != actor:
        send(
            old_owner,
            _("{0} moved: {1}").format(label, title),
            _("{0} transferred {1} {2} to {3}.").format(
                get_fullname(actor), label, doc.name, get_fullname(new_owner)
            ),
            doc.doctype,
            doc.name,
        )
