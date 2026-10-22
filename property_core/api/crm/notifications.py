"""Push notifications — device registration and the in-app notification list.

The app registers its Firebase token after login and drops it on logout.
Every Notification Log written for the user (assignment, follow-up reminder,
transfer, the morning digest, desk mentions) is pushed to those tokens by
frappe_fcm_notification, and is also what ``get_notifications`` lists, so
the bell screen and the pushes are the same records.

Push payload the app receives (FCM ``data``):

    {"doctype": "Lead", "docname": "CRM-LEAD-2026-00012"}

``docname`` is the string "None" for list-level pushes (the morning digest
points at ``Property Follow Up`` with no record) -- open the list then.
"""

import frappe
from frappe import _
from frappe.utils import cint

from property_core.api.crm import base
from property_core.api.utils import ok

DEVICE_TYPES = ("android", "ios", "web")

LIST_FIELDS = [
    "name",
    "subject",
    "email_content",
    "type",
    "document_type",
    "document_name",
    "from_user",
    "read",
    "creation",
]


def _require_fcm():
    if not frappe.db.exists("DocType", "User Device"):
        frappe.throw(_("Push notifications are not set up on this site (frappe_fcm_notification missing)."))


def _user_agent():
    request = getattr(frappe.local, "request", None)
    return (request.headers.get("User-Agent") or "")[:140] if request else None


@frappe.whitelist(methods=["POST"])
def register_device(device_token, device_type="android", device_name=None):
    """Save this phone/browser's FCM token for the logged-in user. Call after
    every login and whenever Firebase hands out a new token.

    A token belongs to one device, so it is taken away from any other user
    first -- otherwise a shared phone keeps pushing the previous user's leads.
    """
    user = base.require_user()
    _require_fcm()

    device_token = (device_token or "").strip()
    if not device_token:
        frappe.throw(_("device_token is required"))
    device_type = (device_type or "android").strip().lower()
    if device_type not in DEVICE_TYPES:
        frappe.throw(_("device_type must be one of {0}").format(", ".join(DEVICE_TYPES)))

    mine = None
    for row in frappe.get_all(
        "User Device", filters={"device_token": device_token}, fields=["name", "user"]
    ):
        if row.user == user and not mine:
            mine = row.name
        else:
            frappe.delete_doc("User Device", row.name, ignore_permissions=True, force=True)

    if mine:
        frappe.db.set_value(
            "User Device",
            mine,
            {"device_type": device_type, "device_name": device_name or None, "is_active": 1},
        )
        return ok(data={"name": mine}, message=_("Device already registered"))

    doc = frappe.get_doc(
        {
            "doctype": "User Device",
            "user": user,
            "device_token": device_token,
            "device_type": device_type,
            "device_name": device_name or _user_agent(),
            "is_active": 1,
        }
    ).insert(ignore_permissions=True)
    return ok(data={"name": doc.name}, message=_("Device registered"))


@frappe.whitelist(methods=["POST"])
def unregister_device(device_token=None, all_devices=0):
    """Logout: stop pushing to this device. ``all_devices=1`` signs the user
    out of push everywhere."""
    user = base.require_user()
    _require_fcm()

    filters = {"user": user}
    if not base.as_bool(all_devices):
        if not device_token:
            frappe.throw(_("device_token is required (or pass all_devices=1)"))
        filters["device_token"] = device_token.strip()

    names = frappe.get_all("User Device", filters=filters, pluck="name")
    for name in names:
        frappe.delete_doc("User Device", name, ignore_permissions=True, force=True)
    return ok(data={"removed": len(names)})


@frappe.whitelist()
def my_devices():
    user = base.require_user()
    _require_fcm()
    rows = frappe.get_all(
        "User Device",
        filters={"user": user},
        fields=["name", "device_type", "device_name", "creation"],
        order_by="creation desc",
    )
    return ok(data=base.serialize(rows))


@frappe.whitelist()
def get_notifications(unread_only=0, page=1, page_size=20):
    """The bell screen, newest first."""
    user = base.require_user()
    page, page_size, start = base.page_args(page, page_size)

    filters = {"for_user": user}
    if base.as_bool(unread_only):
        filters["read"] = 0

    rows = frappe.get_all(
        "Notification Log",
        filters=filters,
        fields=LIST_FIELDS,
        order_by="creation desc",
        limit_start=start,
        limit_page_length=page_size,
    )
    for row in rows:
        row["subject"] = frappe.utils.strip_html(row.get("subject") or "")
        row["body"] = frappe.utils.strip_html(row.pop("email_content") or "") or row["subject"]
    total = frappe.db.count("Notification Log", filters)

    return ok(
        data={
            "rows": base.serialize(rows),
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": start + len(rows) < total,
            "unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0}),
        }
    )


@frappe.whitelist()
def unread_count():
    user = base.require_user()
    return ok(data={"unread": frappe.db.count("Notification Log", {"for_user": user, "read": 0})})


@frappe.whitelist(methods=["POST"])
def mark_read(name=None):
    """One notification read, or all of them when ``name`` is empty."""
    user = base.require_user()
    filters = {"for_user": user, "read": 0}
    if name:
        filters["name"] = name

    names = frappe.get_all("Notification Log", filters=filters, pluck="name")
    for n in names:
        frappe.db.set_value("Notification Log", n, "read", 1, update_modified=False)
    return ok(data={"marked": len(names)})


@frappe.whitelist(methods=["POST"])
def send_test():
    """Push a test message to every device of the logged-in user."""
    from property_core.property_core.notifications.push import send

    user = base.require_user()
    _require_fcm()

    devices = frappe.db.count("User Device", {"user": user})
    if not devices:
        frappe.throw(_("No device registered for {0}. Call register_device first.").format(user))

    name = send(user, _("Test notification"), _("Push notifications are working."), from_user="Administrator")
    return ok(data={"notification": name, "devices": cint(devices)}, message=_("Test push queued"))
