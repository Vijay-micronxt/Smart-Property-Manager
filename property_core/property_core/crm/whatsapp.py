"""WhatsApp from the Lead desk, rendered the same way it is sent.

JD's CRM Lead list did this with a Client Script that built the preview in the
browser from the raw template. The template is a rich-text field, so the
preview showed `<p>` soup and every literal `\\n` somebody had typed into the
editor -- while the message that actually went out had been cleaned
server-side. Preview and reality disagreed.

So the preview is rendered by the same code that sends: whatever comes back
from here is exactly what the customer receives.
"""

import re

import frappe
from frappe import _

BLOCK_TAGS = re.compile(r"</(?:p|div|li|h[1-6])\s*>|<br\s*/?>", re.IGNORECASE)
ANY_TAG = re.compile(r"<[^>]+>")
# Literal backslash-n, /n and %0A typed into the editor as if they were breaks.
TYPED_BREAKS = re.compile(r"%0A|\\n|(?<!\w)/n(?!\w)")

ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&hellip;": "...",
    "&mdash;": "—",
    "&ndash;": "–",
}


def to_plain_text(html):
    """Rich-text template -> what WhatsApp will actually show."""
    if not html:
        return ""

    text = BLOCK_TAGS.sub("\n", html)
    text = ANY_TAG.sub("", text)

    for entity, replacement in ENTITIES.items():
        text = text.replace(entity, replacement)

    text = TYPED_BREAKS.sub("\n", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return "\n".join(line.strip() for line in text.split("\n")).strip()


def _handler():
    """erpnext_enhancements owns the templates and the sending. It may not be
    installed -- a property site without it still gets wa.me links."""
    try:
        from erpnext_enhancements.api.whatsapp_reminders.whatsapp import (
            MessageTemplateHandler,
        )

        return MessageTemplateHandler
    except Exception:
        return None


@frappe.whitelist()
def render_template(doctype, docname, template=None):
    """The message this document + template would send, as plain text."""
    frappe.has_permission(doctype, "read", doc=docname, throw=True)

    if not template:
        return ""

    text = frappe.db.get_value("WhatsApp Message Template", template, "template_text")
    if not text:
        return ""

    handler = _handler()
    if handler:
        try:
            doc = frappe.get_doc(doctype, docname)
            rendered = handler._process_template(text, doc)
            rendered = handler.format_whatsapp_message(rendered)
            if rendered:
                return rendered
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"WhatsApp template render: {template}")

    return _fill_placeholders(to_plain_text(text), doctype, docname)


def _fill_placeholders(text, doctype, docname):
    """Minimal {field} substitution for sites without erpnext_enhancements."""
    doc = frappe.get_doc(doctype, docname)

    def replace(match):
        value = doc.get(match.group(1))
        return str(value) if value is not None else ""

    return re.sub(r"\{(\w+)\}", replace, text)


@frappe.whitelist()
def templates():
    return frappe.get_all(
        "WhatsApp Message Template",
        filters={"is_active": 1},
        fields=["name", "title"],
        order_by="title asc",
    ) if frappe.db.exists("DocType", "WhatsApp Message Template") else []


@frappe.whitelist()
def send(doctype, docname, phone_number, message, template=None):
    """Send through erpnext_enhancements when it is there.

    Returns ``{"sent": False, "link": "..."}`` when it is not, so the browser
    can fall back to opening WhatsApp itself rather than failing.
    """
    frappe.has_permission(doctype, "read", doc=docname, throw=True)

    if not message:
        frappe.throw(_("There is no message to send."))

    try:
        from erpnext_enhancements.api.whatsapp_reminders.whatsapp import (
            send_manual_whatsapp_message,
        )
    except Exception:
        return {"sent": False, "link": wa_link(phone_number, message)}

    result = send_manual_whatsapp_message(
        doctype=doctype,
        docname=docname,
        phone_number=phone_number,
        message=message,
        template_name=template or None,
    )

    if not (result or {}).get("success"):
        return {
            "sent": False,
            "link": wa_link(phone_number, message),
            "error": (result or {}).get("message"),
        }

    _log_follow_up(doctype, docname, phone_number, message)
    return {"sent": True, "phone": result.get("phone_used") or phone_number}


def wa_link(phone_number, message=None):
    digits = "".join(ch for ch in str(phone_number or "") if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    link = f"https://wa.me/{digits}"
    if message:
        from urllib.parse import quote

        link = f"{link}?text={quote(message)}"
    return link


def _log_follow_up(doctype, docname, phone_number, message):
    if doctype not in ("Lead", "Opportunity", "Property Booking", "Property Unit", "Customer"):
        return
    try:
        frappe.get_doc(
            {
                "doctype": "Property Follow Up",
                "reference_doctype": doctype,
                "reference_name": docname,
                "follow_up_type": "WhatsApp",
                "status": "Completed",
                "scheduled_on": frappe.utils.now_datetime(),
                "assigned_to": frappe.session.user,
                "notes": message[:500],
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"WhatsApp follow-up log: {docname}")
