from frappe.model.document import Document

from property_core.property_core.crm.masters import clear_master_cache


class PropertyLeadStatus(Document):
    def on_update(self):
        clear_master_cache()

    def on_trash(self):
        clear_master_cache()

    def after_rename(self, old, new, merge=False):
        clear_master_cache()
