"""What a `bench migrate` is about to change, before you run it.

On a site with developer_mode on, saving a DocType in the desk rewrites the
app's JSON on disk. That has bitten this app twice: a git conflict on two
metadata lines, and Connections rows pointing at a column that had been
renamed. The dangerous version of the same thing is quieter -- a field added
through the desk becomes a DocField, not a Custom Field, and the next migrate
deletes it without a word.

So: run this on the server before migrating. It compares what the database has
against what the app ships and prints anything that would be lost, overridden
or duplicated.

    bench --site <site> execute property_core.property_core.utils.deploy_check.run

Nothing here writes. It is safe to run any time, on any site.
"""

import json
import os

import frappe

APP = "property_core"


def _app_doctypes():
    """Every DocType this app ships, with the path to its JSON."""
    found = {}
    app_path = frappe.get_app_path(APP)

    for root, _dirs, files in os.walk(app_path):
        for name in files:
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            if f"{os.sep}doctype{os.sep}" not in path:
                continue
            try:
                with open(path) as handle:
                    data = json.load(handle)
            except Exception:
                continue
            if data.get("doctype") == "DocType" and data.get("name"):
                found[data["name"]] = data

    return found


def _app_managed_custom_fields():
    """Fieldnames the app creates itself through after_migrate."""
    managed = set()

    for module, attr in (
        ("property_core.property_core.customer_kyc", "CUSTOMER_KYC_FIELDS"),
        ("property_core.property_core.crm_links", "OPPORTUNITY_FIELDS"),
        ("property_core.property_core.crm_links", "ISSUE_FIELDS"),
        ("property_core.property_core.crm.lead_fields", "LEAD_CRM_FIELDS"),
        ("property_core.property_core.crm.lead_fields", "OPPORTUNITY_REQUIREMENT_FIELDS"),
        ("property_core.property_core.crm.telephony", "TELEPHONY_FIELDS"),
        ("property_core.property_core.crm.customer_from_lead", "ADDRESS_FIELDS"),
        ("property_core.property_operations.issue_links", "ISSUE_FIELDS"),
        ("property_core.property_operations.property_unit_links", "PROPERTY_UNIT_FIELDS"),
        ("property_core.property_operations.property_unit_links", "SALES_INVOICE_FIELDS"),
        ("property_core.property_operations.property_unit_links", "SETTINGS_FIELDS"),
        ("property_core.property_core.notifications.custom_fields", "LEAD_FIELDS"),
        ("property_core.property_core.notifications.custom_fields", "SALES_INVOICE_FIELDS"),
        ("property_core.property_core.notifications.custom_fields", "PAYMENT_ENTRY_FIELDS"),
    ):
        try:
            fields = getattr(frappe.get_module(module), attr, []) or []
        except Exception:
            continue
        for field in fields:
            if isinstance(field, dict) and field.get("fieldname"):
                managed.add(field["fieldname"])

    return managed


def run():
    shipped = _app_doctypes()
    managed = _app_managed_custom_fields()
    problems = 0

    print(f"\nChecking {len(shipped)} doctypes shipped by {APP}\n" + "=" * 60)

    # --- fields the database has and the app does not ---------------------
    print("\n1. Fields that migrate would DELETE")
    lost = []
    for name, data in sorted(shipped.items()):
        if not frappe.db.exists("DocType", name):
            continue

        shipped_fields = {f["fieldname"] for f in data.get("fields") or []}
        db_fields = set(
            frappe.get_all("DocField", filters={"parent": name}, pluck="fieldname")
        )
        custom = set(
            frappe.get_all("Custom Field", filters={"dt": name}, pluck="fieldname")
        )

        for field in sorted(db_fields - shipped_fields - custom):
            lost.append(f"   {name}.{field}")

    if lost:
        problems += len(lost)
        print("   Added through the desk, not in the app. Migrate drops these:")
        print("\n".join(lost))
        print("   -> Add them to the app's JSON first, or export them as Custom Fields.")
    else:
        print("   none")

    # --- custom fields nobody in the app owns -----------------------------
    print("\n2. Custom Fields on app doctypes that the app does not create")
    orphans = []
    for name in sorted(shipped):
        for field in frappe.get_all(
            "Custom Field", filters={"dt": name}, fields=["name", "fieldname"]
        ):
            if field.fieldname not in managed:
                shipped_fields = {f["fieldname"] for f in shipped[name].get("fields") or []}
                if field.fieldname in shipped_fields:
                    orphans.append(f"   {field.name}  (duplicates a field the app ships)")
                else:
                    orphans.append(f"   {field.name}")

    if orphans:
        problems += len(orphans)
        print("   These survive migrate, but nothing in the app maintains them:")
        print("\n".join(orphans))
        print("   -> Keep deliberately, or delete once the app covers them.")
    else:
        print("   none")

    # --- property setters quietly overriding the shipped definition -------
    print("\n3. Property Setters overriding app doctypes")
    setters = []
    for name in sorted(shipped):
        for row in frappe.get_all(
            "Property Setter",
            filters={"doc_type": name},
            fields=["name", "field_name", "property", "value"],
        ):
            setters.append(
                f"   {name}.{row.field_name or '(doctype)'} {row.property} = {row.value}"
            )

    if setters:
        print("   Customize Form wins over the JSON for these:")
        print("\n".join(setters))
        print("   -> Harmless if they match the app. Check the ones that do not.")
    else:
        print("   none")

    # --- site scripts on doctypes the app now carries its own JS for ------
    print("\n4. Site scripts on doctypes the app now handles itself")
    app_js = set(frappe.get_hooks("doctype_js") or {}) | set(
        frappe.get_hooks("doctype_list_js") or {}
    )
    scripts = []
    for row in frappe.get_all(
        "Client Script",
        filters={"dt": ["in", list(app_js)], "enabled": 1},
        fields=["name", "dt", "view"],
    ):
        scripts.append(f"   Client Script: {row.name}  ({row.dt} / {row.view})")

    if scripts:
        print("   Both will run. Watch for duplicate buttons or clashing handlers:")
        print("\n".join(scripts))
        print("   -> Disable the ones the app has replaced.")
    else:
        print("   none")

    print("\n" + "=" * 60)
    if problems:
        print(f"{problems} thing(s) need a decision before migrating.\n")
    else:
        print("Nothing would be lost. Safe to migrate.\n")

    return problems
