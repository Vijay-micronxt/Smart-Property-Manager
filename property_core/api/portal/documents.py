"""
Read-only document index for the portal.

Nothing new is stored: this walks what the estate already attaches -- Property
Document rows, the agreement PDF, and File attachments on the customer's own
bookings, units, agreements and invoices -- and returns one flat list with a
usable ``file_url``.

Private files stay behind Frappe's own file permission check; the portal user
must have been granted the file (or it must be public) for the URL to open.
``download_url`` is therefore a link, not a stream -- no endpoint here re-serves
file bytes.
"""

import frappe

from property_core.api.portal.base import (
    as_int,
    assert_unit,
    customer_units,
    get_customer,
    get_list,
    serialize,
)
from property_core.api.utils import ok

# Doctypes whose attachments belong to the customer who owns the parent record.
ATTACHMENT_SOURCES = (
    ("Property Booking", "customer"),
    ("Property Agreement", "customer"),
    ("Property Allocation", "customer"),
    ("Sales Invoice", "customer"),
)


DOWNLOAD = "/api/method/property_core.api.portal.documents.download?file_url="
DRIVE_DOWNLOAD = "/api/method/property_core.api.portal.documents.drive_download?entity="


def _collect(customer, units):
    from urllib.parse import quote

    out = []
    out += _property_documents(units)
    out += _agreement_documents(customer, units)
    out += _attachments(customer, units)
    for row in out:
        # private files do not open for a portal login; this link streams them
        # after checking they are the customer's own
        if row.get("file_url"):
            row["download_url"] = DOWNLOAD + quote(row["file_url"], safe="")
    out += _drive_documents(customer, units)
    return out


@frappe.whitelist()
def list_documents(property_unit=None, limit=200):
    """Every document the customer can see, newest first."""
    customer = get_customer()
    if property_unit:
        assert_unit(customer, property_unit)
    units = [property_unit] if property_unit else customer_units(customer)

    out = _collect(customer, units)

    out.sort(key=lambda r: (r.get("modified") or ""), reverse=True)
    out = out[: as_int(limit, 200)]

    by_source = {}
    for row in out:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1

    return ok(data={"documents": out, "by_source": by_source, "total": len(out)})


def _property_documents(units):
    """Estate-level papers (layout approval, RERA certificate, ...) for the
    properties the customer holds a unit in."""
    if not units:
        return []

    properties = sorted({
        p for p in frappe.get_all(
            "Property Unit", filters={"name": ["in", units]}, pluck="property"
        ) if p
    })
    if not properties:
        return []

    rows = get_list(
        "Property Document",
        {"parent": ["in", properties], "parenttype": "Property"},
        extra_fields=["parent", "modified"],
    )
    return [{
        "source": "Property",
        "reference_doctype": "Property",
        "reference": row.get("parent"),
        "property_unit": None,
        "title": row.get("document_name"),
        "document_type": row.get("document_type"),
        "file_url": row.get("document_file"),
        "expiry_date": row.get("expiry_date"),
        "notes": row.get("notes"),
        "modified": row.get("modified"),
    } for row in rows if row.get("document_file")]


def _agreement_documents(customer, units):
    rows = get_list(
        "Property Agreement",
        {"customer": customer, "document_attachment": ["is", "set"]},
        extra_fields=["modified"],
    )
    return [{
        "source": "Agreement",
        "reference_doctype": "Property Agreement",
        "reference": row["name"],
        "property_unit": row.get("property_unit"),
        "title": frappe._("{0} - {1}").format(row.get("agreement_type") or "Agreement", row["name"]),
        "document_type": row.get("agreement_type"),
        "file_url": row.get("document_attachment"),
        "expiry_date": row.get("end_date"),
        "notes": None,
        "modified": row.get("modified"),
    } for row in rows]


def _attachments(customer, units):
    """File rows attached to documents that belong to this customer."""
    out = []
    for doctype, customer_field in ATTACHMENT_SOURCES:
        filters = {customer_field: customer}
        if doctype in ("Sales Invoice",):
            filters["docstatus"] = 1
        names = frappe.get_all(doctype, filters=filters, pluck="name")
        if not names:
            continue

        files = serialize(frappe.get_all(
            "File",
            filters={"attached_to_doctype": doctype, "attached_to_name": ["in", names]},
            fields=["name", "file_name", "file_url", "is_private", "file_size",
                    "attached_to_name", "modified"],
            order_by="modified desc",
        ))
        for row in files:
            out.append({
                "source": doctype,
                "reference_doctype": doctype,
                "reference": row["attached_to_name"],
                "property_unit": None,
                "title": row.get("file_name"),
                "document_type": None,
                "file_url": row.get("file_url"),
                "is_private": row.get("is_private"),
                "size": row.get("file_size"),
                "expiry_date": None,
                "notes": None,
                "modified": row.get("modified"),
            })
    return out


def _drive_documents(customer, units, max_depth=4):
    """Files the office keeps in each booking's Frappe Drive folder (signed
    agreement, receipts, KYC copies …), read-only for the customer."""
    if "drive" not in frappe.get_installed_apps():
        return []
    folders = frappe.get_all(
        "Property Booking",
        filters={"customer": customer, "docstatus": 1, "drive_folder_id": ["is", "set"]},
        fields=["name", "property_unit", "drive_folder_id"],
    )
    out = []
    for booking in folders:
        if units and booking.property_unit not in units:
            continue
        frontier, depth = [(booking.drive_folder_id, "")], 0
        while frontier and depth < max_depth:
            nxt = []
            for folder, path in frontier:
                for f in frappe.get_all(
                    "Drive File",
                    filters={"parent_entity": folder, "is_active": 1},
                    fields=["name", "title", "is_group", "file_size", "mime_type", "modified"],
                ):
                    if f.is_group:
                        nxt.append((f.name, f"{path}{f.title}/"))
                        continue
                    out.append({
                        "source": "Drive",
                        "reference_doctype": "Property Booking",
                        "reference": booking.name,
                        "property_unit": booking.property_unit,
                        "title": f.title,
                        "folder": path.rstrip("/") or None,
                        "document_type": f.mime_type,
                        "file_url": None,
                        "download_url": DRIVE_DOWNLOAD + f.name,
                        "size": f.file_size,
                        "expiry_date": None,
                        "notes": None,
                        "modified": str(f.modified),
                    })
            frontier, depth = nxt, depth + 1
    return out


@frappe.whitelist()
def download(file_url):
    """Stream one of the customer's own documents (the ``download_url`` on
    every list_documents row). Anything not in their document list is refused."""
    customer = get_customer()
    allowed = {row.get("file_url") for row in _collect(customer, customer_units(customer)) if row.get("file_url")}
    if file_url not in allowed:
        frappe.throw(frappe._("This document is not on your account."), frappe.PermissionError)
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        frappe.throw(frappe._("File not found"), frappe.DoesNotExistError)
    _send(frappe.get_doc("File", name).get_content(), frappe.db.get_value("File", name, "file_name"))


@frappe.whitelist()
def drive_download(entity):
    """Stream a file from one of the customer's booking folders in Drive."""
    customer = get_customer()
    allowed = {row["download_url"].rsplit("=", 1)[1] for row in _drive_documents(customer, customer_units(customer))}
    if entity not in allowed:
        frappe.throw(frappe._("This document is not on your account."), frappe.PermissionError)
    from drive.utils.files import FileManager

    f = frappe.get_value("Drive File", entity, ["name", "title", "path", "team", "mime_type", "document"], as_dict=True)
    _send(FileManager().get_file(f).read(), f.title)


def _send(content, filename):
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
