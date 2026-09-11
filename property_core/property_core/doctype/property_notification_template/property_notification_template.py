import frappe
from frappe.model.document import Document


class PropertyNotificationTemplate(Document):
    def validate(self):
        self.validate_jinja()
        self.enforce_single_default()

    def validate_jinja(self):
        from frappe.utils.jinja import get_jenv

        for fieldname in ("subject", "message"):
            source = self.get(fieldname)
            if not source:
                continue
            try:
                get_jenv().from_string(source)
            except Exception as e:
                frappe.throw(
                    frappe._("{0} is not valid Jinja: {1}").format(
                        self.meta.get_label(fieldname), frappe.utils.cstr(e)
                    )
                )

    def enforce_single_default(self):
        if not self.is_default:
            return
        others = frappe.get_all(
            "Property Notification Template",
            filters={
                "event": self.event,
                "channel": self.channel,
                "is_default": 1,
                "name": ["!=", self.name],
            },
            pluck="name",
        )
        for other in others:
            frappe.db.set_value("Property Notification Template", other, "is_default", 0)


def get_template(event, channel):
    """Default template for an event+channel, or None to fall back to the
    built-in message in notifications/defaults.py."""
    if not frappe.db.exists("DocType", "Property Notification Template"):
        return None

    name = frappe.db.get_value(
        "Property Notification Template",
        {"event": event, "channel": channel, "enabled": 1, "is_default": 1},
        "name",
    ) or frappe.db.get_value(
        "Property Notification Template",
        {"event": event, "channel": channel, "enabled": 1},
        "name",
    )
    if not name:
        return None
    return frappe.get_cached_doc("Property Notification Template", name)
