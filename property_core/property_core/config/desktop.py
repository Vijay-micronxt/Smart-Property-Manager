from frappe import _

def get_data():
    return [
        {
            "module_name": "Property Core",
            "color": "#3498db",
            "icon": "octicon octicon-home",
            "type": "module",
            "label": _("Property Core"),
            "description": _("Property inventory, booking, allocation and agreements"),
        }
    ]
