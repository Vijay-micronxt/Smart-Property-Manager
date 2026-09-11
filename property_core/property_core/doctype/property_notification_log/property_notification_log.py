import frappe
from frappe.model.document import Document


class PropertyNotificationLog(Document):
    pass


@frappe.whitelist()
def retry(log_name):
    """Manual retry from the log form. Re-sends the exact stored payload."""
    from property_core.property_core.notifications.dispatcher import resend_log

    frappe.only_for(("System Manager", "Property Manager"))
    return resend_log(log_name)
