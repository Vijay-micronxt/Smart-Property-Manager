"""Delivery channels for property notifications.

Two channels, one contract: every ``send_*`` returns a provider response dict on
success and raises :class:`DeliveryError` on failure. The dispatcher turns that
into a Sent/Failed row in Property Notification Log -- nothing here writes logs
itself.
"""

import json
import re

import frappe
from frappe.utils import cstr, get_url

from property_core.property_core.doctype.property_notification_settings.property_notification_settings import (
    get_settings,
)


class DeliveryError(Exception):
    pass


# --------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------

def outgoing_email_available():
    """True when at least one Email Account can actually send.

    Worth checking up front: a site with every outgoing account disabled fails
    every single email, and the error Frappe raises then ("Please set default
    Email Account") is not obviously about the notification at all.
    """
    return bool(
        frappe.db.exists("Email Account", {"enable_outgoing": 1, "default_outgoing": 1})
        or frappe.db.exists("Email Account", {"enable_outgoing": 1})
    )


def send_email(recipient, subject, message, attachments=None, reference_doctype=None, reference_name=None):
    settings = get_settings()

    if not outgoing_email_available():
        raise DeliveryError(
            "No Email Account on this site has outgoing enabled. "
            "Configure one under Settings > Email Account before enabling the Email channel."
        )

    kwargs = {
        "recipients": [recipient],
        "subject": subject or "Notification",
        "message": message,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "attachments": attachments or [],
        "now": True,
        "expose_recipients": "header",
    }
    if settings and settings.email_sender:
        kwargs["sender"] = settings.email_sender
    if settings and settings.email_reply_to:
        kwargs["reply_to"] = settings.email_reply_to

    try:
        frappe.sendmail(**kwargs)
    except Exception as e:
        raise DeliveryError(cstr(e))

    return {"channel": "Email", "recipient": recipient}


# --------------------------------------------------------------------------
# WhatsApp
# --------------------------------------------------------------------------

def clean_mobile(number, country_code="91"):
    """Strip formatting and return a bare international number, or None."""
    if not number:
        return None

    digits = re.sub(r"\D", "", cstr(number))
    if not digits:
        return None

    # 00-prefixed international form
    if digits.startswith("00"):
        digits = digits[2:]

    country_code = re.sub(r"\D", "", cstr(country_code or "")) or "91"

    # A bare 10-digit Indian number, or any number shorter than country code +
    # subscriber, gets the default country code prefixed.
    if len(digits) <= 10:
        digits = country_code + digits.lstrip("0")

    if len(digits) < 10 or len(digits) > 15:
        return None

    return digits


def send_whatsapp(mobile, message, media_url=None, file_name=None):
    settings = get_settings()
    if not settings:
        raise DeliveryError("Property Notification Settings not available on this site.")

    provider, credentials = settings.get_whatsapp_credentials()
    if not credentials:
        raise DeliveryError(
            f"WhatsApp provider '{provider}' is not configured. "
            "Fill in the credentials in Property Notification Settings."
        )

    number = clean_mobile(mobile, settings.default_country_code)
    if not number:
        raise DeliveryError(f"Invalid mobile number: {mobile!r}")

    if provider == "Meta Cloud API":
        return _send_meta(credentials, number, message, media_url, file_name)
    return _send_botmaster(credentials, number, message, media_url, file_name)


def _post(url, **kwargs):
    import requests

    try:
        return requests.post(url, timeout=30, **kwargs)
    except Exception as e:
        raise DeliveryError(f"HTTP call to provider failed: {cstr(e)}")


def _botmaster_ok(response):
    """BotMaster answers 200 even for application-level errors, so the body has
    to be inspected rather than just the status code."""
    if response.status_code != 200:
        return False

    body = (response.text or "").strip()
    lowered = body.lower()
    if any(token in lowered for token in ("error", "not found", "invalid", "fail")):
        return False

    try:
        parsed = json.loads(body)
    except ValueError:
        return bool(body)

    if isinstance(parsed, dict):
        status = cstr(parsed.get("status") or parsed.get("Status") or "").lower()
        if status in ("false", "error", "failed"):
            return False
    return True


def _send_botmaster(credentials, number, message, media_url=None, file_name=None):
    base_url = credentials["api_url"]
    payload = {
        "senderId": credentials["sender_id"],
        "authToken": credentials["auth_token"],
        "receiverId": number,
    }

    if media_url:
        media_payload = dict(
            payload,
            mediaUrl=media_url,
            fileName=file_name or "attachment.pdf",
            messageText=message or "",
        )
        response = _post(base_url.replace("action=send", "action=sendmedia"), data=media_payload)
        if _botmaster_ok(response):
            return {
                "channel": "WhatsApp",
                "provider": "BotMaster API",
                "mode": "media",
                "recipient": number,
                "response": response.text[:1000],
            }

        # sendmedia is not enabled on every BotMaster account. Rather than fail,
        # fall through to a text message carrying the download link -- the
        # recipient still gets the document, and the log records the downgrade.
        message = "{}\n\n{}".format(message or "", media_url).strip()
        media_downgraded = response.text[:300]
    else:
        media_downgraded = None

    response = _post(base_url, data=dict(payload, messageText=message or ""))
    if not _botmaster_ok(response):
        raise DeliveryError(f"BotMaster rejected the message: {response.text[:500]}")

    result = {
        "channel": "WhatsApp",
        "provider": "BotMaster API",
        "mode": "text",
        "recipient": number,
        "response": response.text[:1000],
    }
    if media_downgraded:
        result["media_fallback_reason"] = media_downgraded
    return result


def _send_meta(credentials, number, message, media_url=None, file_name=None):
    url = "https://graph.facebook.com/{}/{}/messages".format(
        credentials["api_version"], credentials["phone_number_id"]
    )
    headers = {
        "Authorization": "Bearer {}".format(credentials["access_token"]),
        "Content-Type": "application/json",
    }

    if media_url:
        body = {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "document",
            "document": {
                "link": media_url,
                "filename": file_name or "attachment.pdf",
                "caption": (message or "")[:1024],
            },
        }
    else:
        body = {
            "messaging_product": "whatsapp",
            "to": number,
            "type": "text",
            "text": {"preview_url": False, "body": message or ""},
        }

    response = _post(url, headers=headers, data=json.dumps(body))
    if response.status_code >= 300:
        raise DeliveryError(f"Meta Cloud API returned {response.status_code}: {response.text[:500]}")

    return {
        "channel": "WhatsApp",
        "provider": "Meta Cloud API",
        "mode": "document" if media_url else "text",
        "recipient": number,
        "response": response.text[:1000],
    }


# --------------------------------------------------------------------------
# PDF generation
# --------------------------------------------------------------------------

def build_pdf_attachment(doc, print_format=None, public=False, label=None):
    """Render ``doc`` to a PDF File and return (file_url, file_name).

    WhatsApp providers fetch the document over plain HTTP, so a WhatsApp
    attachment has to be a public File. The filename carries a 32-char random
    token so the URL cannot be guessed from the invoice number -- but it is
    still an unauthenticated link, so only turn on WhatsApp PDF attachments if
    that trade-off is acceptable.
    """
    from frappe.utils.print_format import download_pdf  # noqa: F401  (ensures print deps load)

    base = "{}-{}".format(label or doc.doctype.replace(" ", "-"), doc.name)
    file_name = "{}.pdf".format(base)

    existing = frappe.db.get_value(
        "File",
        {
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
            "is_private": 0 if public else 1,
            # public files carry a random token: "<base>-<hash>.pdf"
            "file_name": ["like", "{}-%".format(base) if public else file_name],
        },
        ["file_url", "file_name"],
    )
    if existing:
        return existing[0], existing[1]

    pdf_content = frappe.get_print(
        doc.doctype,
        doc.name,
        print_format=print_format or None,
        as_pdf=True,
        no_letterhead=0,
    )

    if public:
        file_name = "{}-{}.pdf".format(base, frappe.generate_hash(length=32))

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "attached_to_doctype": doc.doctype,
        "attached_to_name": doc.name,
        "is_private": 0 if public else 1,
        "content": pdf_content,
    })
    file_doc.save(ignore_permissions=True)

    return file_doc.file_url, file_doc.file_name


def absolute_url(file_url):
    if not file_url:
        return None
    if file_url.startswith("http"):
        return file_url
    return get_url(file_url)
