import frappe
from frappe.model.document import Document


DEFAULT_REMINDER_RULES = [
    {"label": "7 days before due", "offset_days": -7, "channel": "Both"},
    {"label": "3 days before due", "offset_days": -3, "channel": "Both"},
    {"label": "On due date", "offset_days": 0, "channel": "Both"},
    {
        "label": "Overdue weekly",
        "offset_days": 3,
        "repeat_after_offset": 1,
        "repeat_every_days": 7,
        "stop_after_days": 90,
        "channel": "Both",
    },
]


class PropertyNotificationSettings(Document):
    def validate(self):
        self.validate_reminder_rules()

    def validate_reminder_rules(self):
        seen = set()
        for row in self.payment_reminder_rules or []:
            if row.repeat_after_offset and int(row.repeat_every_days or 0) < 1:
                frappe.throw(
                    frappe._("Row {0}: 'Repeat Every (Days)' must be at least 1 when Repeat is ticked.").format(row.idx)
                )
            key = int(row.offset_days or 0)
            if key in seen:
                frappe.throw(
                    frappe._("Row {0}: another rule already uses offset {1}. Offsets must be unique.").format(row.idx, key)
                )
            seen.add(key)

    def get_whatsapp_credentials(self):
        """Returns (provider, credentials dict) or (provider, None) when unusable.

        Falls back to erpnext_enhancements' 'WhatsApp Settings' when this app's
        own fields are blank and `borrow_external_credentials` is ticked, so a
        site that already runs that stack does not have to re-enter the token.
        """
        provider = self.whatsapp_provider or "BotMaster API"

        if provider == "Meta Cloud API":
            token = self.get_password("meta_access_token", raise_exception=False)
            if self.meta_phone_number_id and token:
                return provider, {
                    "api_version": self.meta_api_version or "v19.0",
                    "phone_number_id": self.meta_phone_number_id,
                    "access_token": token,
                }
            return provider, self._borrow_meta_credentials()

        token = self.get_password("botmaster_auth_token", raise_exception=False)
        if self.botmaster_sender_id and token:
            return provider, {
                "api_url": self.botmaster_api_url or "https://api.botmastersender.com/api/v2/?action=send",
                "sender_id": self.botmaster_sender_id,
                "auth_token": token,
            }
        return provider, self._borrow_botmaster_credentials()

    def _external_settings(self):
        if not self.borrow_external_credentials:
            return None
        if not frappe.db.exists("DocType", "WhatsApp Settings"):
            return None
        try:
            return frappe.get_single("WhatsApp Settings")
        except Exception:
            return None

    def _borrow_botmaster_credentials(self):
        external = self._external_settings()
        if not external:
            return None
        sender_id = getattr(external, "sender_id", None)
        token = getattr(external, "auth_token", None)
        if not (sender_id and token):
            return None
        return {
            "api_url": self.botmaster_api_url or "https://api.botmastersender.com/api/v2/?action=send",
            "sender_id": sender_id,
            "auth_token": token,
            "borrowed": True,
        }

    def _borrow_meta_credentials(self):
        external = self._external_settings()
        if not external:
            return None
        phone_number_id = getattr(external, "meta_sender_id", None)
        token = getattr(external, "meta_auth_token", None)
        if not (phone_number_id and token):
            return None
        return {
            "api_version": self.meta_api_version or "v19.0",
            "phone_number_id": phone_number_id,
            "access_token": token,
            "borrowed": True,
        }

    def get_lead_stop_statuses(self):
        raw = self.lead_stop_statuses or ""
        return [s.strip() for s in raw.splitlines() if s.strip()]


def get_settings():
    """Safe accessor -- returns None instead of blowing up when the DocType has
    not been migrated onto the site yet, or during install/migrate."""
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
        return None
    if not frappe.db.exists("DocType", "Property Notification Settings"):
        return None
    try:
        return frappe.get_cached_doc("Property Notification Settings")
    except Exception:
        return None


def seed_default_reminder_rules():
    """after_migrate hook -- gives a brand new site a working reminder schedule
    instead of an empty table that silently sends nothing."""
    if not frappe.db.exists("DocType", "Property Notification Settings"):
        return

    doc = frappe.get_single("Property Notification Settings")
    if doc.payment_reminder_rules:
        return

    for rule in DEFAULT_REMINDER_RULES:
        doc.append("payment_reminder_rules", dict(rule, enabled=1))

    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.commit()
