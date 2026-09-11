"""Central send-and-log path for every property notification.

Every feature module (invoice delivery, payment reminders, lead follow-ups,
receipts) funnels through :func:`notify`. That is what makes the acceptance
criteria hold globally rather than per-feature: one place decides channels,
one place de-duplicates, one place records delivery status, one place records
failures.

Delivery itself is enqueued, so a submit never blocks on an SMTP or WhatsApp
round trip and a provider outage can never roll back the business document.
"""

import json

import frappe
from frappe.utils import cint, cstr, get_url, now_datetime

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)
from property_core.property_core.doctype.property_notification_template.property_notification_template import (
    get_template,
)
from property_core.property_core.notifications import channels as ch
from property_core.property_core.notifications.defaults import get_default

QUEUE = "short"


def notify(
    event,
    doc,
    channel="Both",
    recipient=None,
    context=None,
    attachment=None,
    dedupe_key=None,
    rule_label=None,
    enqueue=True,
):
    """Render and deliver ``event`` for ``doc``.

    :param recipient: dict with any of ``email``, ``mobile``, ``name``,
        ``party_type``, ``party``. Missing addresses produce a Skipped log row
        rather than an exception -- a customer without a mobile number must not
        break invoice submission.
    :param dedupe_key: stable string identifying this exact reminder. A second
        call with the same key and channel is skipped, which is what stops a
        scheduler re-run from double-messaging a customer.
    :returns: list of Property Notification Log names created.
    """
    settings = get_settings()
    if not settings or not settings.enabled:
        return []

    recipient = recipient or {}
    context = context or {}
    logs = []

    for chan in _resolve_channels(channel, settings):
        log_name = _queue_one(
            settings=settings,
            event=event,
            doc=doc,
            chan=chan,
            recipient=recipient,
            context=context,
            attachment=attachment,
            dedupe_key=dedupe_key,
            rule_label=rule_label,
            enqueue=enqueue,
        )
        if log_name:
            logs.append(log_name)

    return logs


def _resolve_channels(channel, settings):
    wanted = ["Email", "WhatsApp"] if channel in (None, "", "Both") else [channel]
    active = []
    if "Email" in wanted and settings.email_enabled:
        active.append("Email")
    if "WhatsApp" in wanted and settings.whatsapp_enabled:
        active.append("WhatsApp")
    return active


def _queue_one(settings, event, doc, chan, recipient, context, attachment, dedupe_key, rule_label, enqueue):
    key = f"{dedupe_key}::{chan}" if dedupe_key else None
    if key and _already_handled(key):
        return None

    address = recipient.get("email") if chan == "Email" else recipient.get("mobile")

    log = frappe.new_doc("Property Notification Log")
    log.event = event
    log.channel = chan
    log.reference_doctype = doc.doctype
    log.reference_name = doc.name
    log.rule_label = rule_label
    log.recipient_name = recipient.get("name")
    log.party_type = recipient.get("party_type")
    log.party = recipient.get("party")
    log.dedupe_key = key
    log.attempt = 1

    if not address:
        log.status = "Skipped"
        log.error = (
            "No email address on record for this recipient."
            if chan == "Email"
            else "No mobile number on record for this recipient."
        )
        log.flags.ignore_permissions = True
        log.insert(ignore_permissions=True)
        return log.name

    log.recipient = address

    try:
        subject, message = render(event, chan, doc, recipient, context)
    except Exception:
        log.status = "Failed"
        log.recipient = address
        log.error = frappe.get_traceback()
        log.flags.ignore_permissions = True
        log.insert(ignore_permissions=True)
        return log.name

    log.subject = subject
    log.message = message

    if attachment:
        log.attachment = attachment.get("public_url") if chan == "WhatsApp" else attachment.get("file_url")

    if settings.test_mode:
        redirected = settings.test_email if chan == "Email" else settings.test_mobile_no
        if not redirected:
            log.status = "Skipped"
            log.error = "Test Mode is on but no test recipient is configured for this channel."
            log.flags.ignore_permissions = True
            log.insert(ignore_permissions=True)
            return log.name
        log.error = f"Test Mode: intended recipient was {address}"
        log.recipient = redirected

    log.status = "Queued"
    log.flags.ignore_permissions = True
    log.insert(ignore_permissions=True)

    if enqueue:
        frappe.enqueue(
            "property_core.property_core.notifications.dispatcher.deliver",
            queue=QUEUE,
            log_name=log.name,
            enqueue_after_commit=True,
        )
    else:
        deliver(log.name)

    return log.name


def describe(log_names):
    """Per-channel outcome for a set of log rows.

    Manual 'send now' buttons need this: `notify` returns a row for a skipped
    channel too, so counting rows alone would report success when nothing
    actually went anywhere.
    """
    if not log_names:
        return []
    return frappe.get_all(
        "Property Notification Log",
        filters={"name": ["in", log_names]},
        fields=["name", "channel", "status", "recipient", "error"],
        order_by="channel",
    )


def _already_handled(key):
    return bool(
        frappe.db.exists(
            "Property Notification Log",
            {"dedupe_key": key, "status": ["in", ["Sent", "Queued"]]},
        )
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render(event, chan, doc, recipient, context):
    template = get_template(event, chan)
    if template:
        subject_source = template.subject
        message_source = template.message
    else:
        fallback = get_default(event, chan)
        if not fallback:
            raise ValueError(f"No template or built-in default for event '{event}' on {chan}.")
        subject_source = fallback.get("subject")
        message_source = fallback.get("message")

    ctx = _build_context(doc, recipient, context)
    subject = frappe.render_template(subject_source, ctx) if subject_source else None
    message = frappe.render_template(message_source, ctx)

    if chan == "WhatsApp":
        message = _collapse_blank_lines(message)

    return subject, message


def _build_context(doc, recipient, extra):
    company = (
        extra.get("company")
        or doc.get("company")
        or frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )
    ctx = {
        "doc": doc,
        "recipient_name": recipient.get("name") or "Customer",
        "company": company,
        "portal_link": get_url("/customer-portal"),
        "days_overdue": 0,
    }
    ctx.update(extra)
    return ctx


def _collapse_blank_lines(text):
    """Jinja `{% if %}` blocks leave stray blank lines; WhatsApp shows them."""
    lines = [line.rstrip() for line in cstr(text).splitlines()]
    cleaned = []
    for line in lines:
        if not line and cleaned and not cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


# --------------------------------------------------------------------------
# Delivery
# --------------------------------------------------------------------------

def deliver(log_name):
    """Send one queued log row. Never raises -- the outcome lands in the row."""
    try:
        log = frappe.get_doc("Property Notification Log", log_name)
    except frappe.DoesNotExistError:
        return

    if log.status == "Sent":
        return

    attachments = []
    media_url = None
    file_name = None
    if log.attachment:
        if log.channel == "Email":
            attachments = [{"file_url": log.attachment}]
        else:
            media_url = ch.absolute_url(log.attachment)
            file_name = log.attachment.rsplit("/", 1)[-1]

    try:
        if log.channel == "Email":
            response = ch.send_email(
                recipient=log.recipient,
                subject=log.subject,
                message=log.message,
                attachments=attachments,
                reference_doctype=log.reference_doctype,
                reference_name=log.reference_name,
            )
        else:
            response = ch.send_whatsapp(
                mobile=log.recipient,
                message=log.message,
                media_url=media_url,
                file_name=file_name,
            )
    except Exception as e:
        error = frappe.get_traceback() if not isinstance(e, ch.DeliveryError) else cstr(e)
        log.db_set(
            {
                "status": "Failed",
                "error": (cstr(log.error) + "\n" if log.error else "") + error,
            },
            update_modified=False,
        )
        frappe.db.commit()
        return

    log.db_set(
        {
            "status": "Sent",
            "sent_on": now_datetime(),
            "provider_response": json.dumps(response, default=str)[:5000],
        },
        update_modified=False,
    )
    frappe.db.commit()


def retry_failed():
    """Daily job -- one more go at anything that failed under the retry cap."""
    settings = get_settings()
    if not settings or not settings.enabled:
        return

    max_retries = cint(settings.max_retries)
    if max_retries < 1:
        return

    rows = frappe.get_all(
        "Property Notification Log",
        filters={"status": "Failed", "attempt": ["<", max_retries + 1]},
        pluck="name",
        limit=500,
    )
    for name in rows:
        attempt = cint(frappe.db.get_value("Property Notification Log", name, "attempt"))
        frappe.db.set_value(
            "Property Notification Log", name, {"attempt": attempt + 1, "status": "Queued"},
            update_modified=False,
        )
        frappe.enqueue(
            "property_core.property_core.notifications.dispatcher.deliver",
            queue=QUEUE,
            log_name=name,
            enqueue_after_commit=True,
        )


def purge_old_logs():
    settings = get_settings()
    if not settings:
        return
    days = cint(settings.log_retention_days)
    if days < 1:
        return

    frappe.db.sql(
        """
        DELETE FROM `tabProperty Notification Log`
        WHERE creation < DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """,
        (days,),
    )


@frappe.whitelist()
def resend_log(log_name):
    log = frappe.get_doc("Property Notification Log", log_name)
    log.db_set({"status": "Queued", "attempt": cint(log.attempt) + 1}, update_modified=False)
    frappe.enqueue(
        "property_core.property_core.notifications.dispatcher.deliver",
        queue=QUEUE,
        log_name=log.name,
        enqueue_after_commit=True,
    )
    return {"queued": log.name}
