"""Files: attachments on records, and the Frappe Drive folders JD keeps
documents in.

Attachments (``attach`` / ``get_attachments`` / ``remove_attachment``) are
plain Frappe files on a record -- the paperclip on the desk form. Send the
file either as multipart (``file`` field) or as ``content`` in base64 with a
``filename``. Pass ``fieldname`` to also put the file into an Attach field of
the record (Property.layout_image, Property Agreement.document_attachment,
a Property Document row …).

Drive (``drive_*``): every Property has a folder tree (01 - Land & Legal …
09 - Handover) and every confirmed booking a folder under
06 - Sales & CRM / Booking Documents. These endpoints find the folder for a
record, list it, create subfolders and upload into it. A folder can only be
reached through a record the caller can read, and only inside that record's
own tree.
"""

import base64

import frappe
from frappe import _

from property_core.api.crm import base
from property_core.api.utils import ok

#: records files can be attached to through this API
ATTACHABLE = {
    "Lead",
    "Opportunity",
    "Customer",
    "Property Booking",
    "Property",
    "Property Unit",
    "Project",
    "Task",
    "Property Allocation",
    "Property Agreement",
    "Property Follow Up",
    "Sales Invoice",
    "Payment Entry",
    "Work Order",
    "Issue",
}

MAX_BYTES = 25 * 1024 * 1024


# --------------------------------------------------------------------------- #
# attachments
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def attach(doctype, name, filename=None, content=None, fieldname=None, is_private=1):
    doc = _record(doctype, name, "write")
    filename, data = _incoming(filename, content)

    file = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": filename,
            "attached_to_doctype": doctype,
            "attached_to_name": name,
            "attached_to_field": fieldname,
            "is_private": 1 if base.as_bool(is_private, True) else 0,
            "content": data,
        }
    )
    file.save(ignore_permissions=True)

    if fieldname:
        field = doc.meta.get_field(fieldname)
        if not field or field.fieldtype not in ("Attach", "Attach Image"):
            frappe.throw(_("{0} is not an attach field on {1}").format(fieldname, doctype))
        doc.set(fieldname, file.file_url)
        doc.save()

    return ok(data=_file_row(file), message=_("{0} attached").format(filename))


@frappe.whitelist()
def get_attachments(doctype, name):
    _record(doctype, name, "read")
    rows = frappe.get_all(
        "File",
        filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0},
        fields=["name", "file_name", "file_url", "file_size", "is_private", "attached_to_field", "owner", "creation"],
        order_by="creation desc",
    )
    return ok(data=base.serialize(rows))


@frappe.whitelist()
def remove_attachment(name):
    file = frappe.get_doc("File", name)
    if not file.attached_to_doctype:
        frappe.throw(_("Not an attachment"), frappe.PermissionError)
    doc = _record(file.attached_to_doctype, file.attached_to_name, "write")
    if file.attached_to_field and doc.get(file.attached_to_field) == file.file_url:
        doc.set(file.attached_to_field, None)
        doc.save()
    frappe.delete_doc("File", name, ignore_permissions=True)
    return ok(data={"name": name}, message=_("Attachment removed"))


# --------------------------------------------------------------------------- #
# drive
# --------------------------------------------------------------------------- #

@frappe.whitelist()
def drive_folder(doctype, name, create=1):
    """The Drive folder of a Property, Property Booking, Property Unit (its
    booking's) or Project (its first property's tree). ``create=1`` builds it
    when missing -- the same tree the desk builds."""
    _record(doctype, name, "read")
    if not _drive_installed():
        return ok(data={"drive": False, "folder": None}, message=_("Frappe Drive is not installed on this site"))
    folder = _folder_of(doctype, name, base.as_bool(create, True))
    return ok(data={"drive": True, **_folder_row(folder)} if folder else {"drive": True, "folder": None})


@frappe.whitelist()
def drive_list(doctype, name, folder=None):
    """Contents of the record's folder, or of ``folder`` inside it."""
    root = _root_or_throw(doctype, name)
    folder = folder or root
    _inside(folder, root)
    rows = frappe.get_all(
        "Drive File",
        filters={"parent_entity": folder, "is_active": 1},
        fields=["name", "title", "is_group", "mime_type", "file_size", "owner", "modified"],
        order_by="is_group desc, title asc",
    )
    for row in rows:
        if not row.is_group:
            row["download_url"] = f"/api/method/drive.api.files.get_file_content?entity_name={row.name}&trigger_download=1"
    return ok(
        data={
            "folder": _folder_row(folder),
            "breadcrumbs": _breadcrumbs(folder, root),
            "items": base.serialize(rows),
        }
    )


@frappe.whitelist()
def drive_create_folder(doctype, name, title, parent=None):
    from property_core.property_core.utils.drive_folders import get_or_create_folder

    _record(doctype, name, "write")
    root = _root_or_throw(doctype, name)
    parent = parent or root
    _inside(parent, root)
    team = frappe.db.get_value("Drive File", parent, "team")
    folder = get_or_create_folder(title.strip(), parent, team)
    return ok(data=_folder_row(folder), message=_("Folder {0} ready").format(title))


@frappe.whitelist()
def drive_upload(doctype, name, folder=None, filename=None, content=None):
    """Upload into the record's Drive folder (or ``folder`` inside it).
    Multipart ``file`` or base64 ``content`` + ``filename``.

    The file is written by Drive's own uploader, so Drive's rules apply: the
    caller needs upload access to that team's folder (JD staff already do,
    they use Drive on the desk)."""
    _record(doctype, name, "write")
    root = _root_or_throw(doctype, name)
    folder = folder or root
    _inside(folder, root)
    team = frappe.db.get_value("Drive File", folder, "team")

    from drive.api.files import upload_file

    if not (frappe.request and frappe.request.files.get("file")):
        # Drive only reads multipart; wrap a base64 body so it looks like one
        filename, data = _incoming(filename, content)
        from io import BytesIO

        from werkzeug.datastructures import FileStorage

        frappe.request.files = {"file": FileStorage(stream=BytesIO(data), filename=filename)}
    # Drive appends chunks to a temp file keyed by this id; without a fresh
    # one every upload lands on "None_<filename>" and can append to a leftover
    frappe.form_dict.uuid = frappe.generate_hash(length=16)
    frappe.form_dict.pop("chunk_index", None)
    result = upload_file(team=team, parent=folder)
    if not result:
        frappe.throw(_("Upload did not complete"))
    return ok(data=_folder_row(result.name) | {"is_group": 0}, message=_("Uploaded"))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _record(doctype, name, ptype):
    if doctype not in ATTACHABLE:
        frappe.throw(_("Files cannot be managed on {0} through this API").format(doctype), frappe.PermissionError)
    doc = base.read_doc(doctype, name)
    if ptype != "read":
        doc.check_permission(ptype)
    return doc


def _incoming(filename, content):
    upload = frappe.request.files.get("file") if frappe.request and frappe.request.files else None
    if upload:
        data = upload.stream.read()
        filename = filename or upload.filename
    elif content:
        if "," in content[:100] and content.startswith("data:"):
            content = content.split(",", 1)[1]
        data = base64.b64decode(content)
    else:
        frappe.throw(_("Send a file (multipart 'file') or base64 'content'"), frappe.MandatoryError)
    if not filename:
        frappe.throw(_("filename is required"), frappe.MandatoryError)
    if len(data) > MAX_BYTES:
        frappe.throw(_("File is larger than {0} MB").format(MAX_BYTES // (1024 * 1024)))
    return filename, data


def _file_row(file):
    return base.serialize(
        {
            "name": file.name,
            "file_name": file.file_name,
            "file_url": file.file_url,
            "file_size": file.file_size,
            "is_private": file.is_private,
            "attached_to_field": file.attached_to_field,
        }
    )


def _drive_installed():
    from property_core.property_core.utils.drive_folders import drive_installed

    return drive_installed()


def _folder_of(doctype, name, create):
    from property_core.property_core.utils import drive_folders as df

    active = lambda f: f and frappe.db.exists("Drive File", {"name": f, "is_active": 1})

    if doctype == "Property":
        folder = frappe.db.get_value("Property", name, "drive_folder_id")
        if not active(folder) and create:
            folder = df.ensure_property_folders(name)
        return folder if active(folder) else None

    if doctype == "Property Unit":
        booking = frappe.db.get_value("Property Booking", {"property_unit": name, "docstatus": 1}, "name")
        if booking:
            return _folder_of("Property Booking", booking, create)
        return _folder_of("Property", frappe.db.get_value("Property Unit", name, "property"), create)

    if doctype == "Property Booking":
        folder = frappe.db.get_value("Property Booking", name, "drive_folder_id")
        if not active(folder) and create:
            folder = df.ensure_booking_folder(frappe.get_doc("Property Booking", name))
        return folder if active(folder) else None

    if doctype == "Project":
        if frappe.get_meta("Project").has_field("drive_folder_id"):
            folder = frappe.db.get_value("Project", name, "drive_folder_id")
            if active(folder):
                return folder
        prop = frappe.db.get_value("Property", {"project": name}, "name")
        return _folder_of("Property", prop, create) if prop else None

    return None


def _root_or_throw(doctype, name):
    _record(doctype, name, "read")
    if not _drive_installed():
        frappe.throw(_("Frappe Drive is not installed on this site"))
    folder = _folder_of(doctype, name, True)
    if not folder:
        frappe.throw(_("No Drive folder for {0} {1}").format(doctype, name))
    return folder


def _inside(folder, root):
    """Refuse any folder outside the record's own tree."""
    current, hops = folder, 0
    while current and hops < 30:
        if current == root:
            return
        current = frappe.db.get_value("Drive File", current, "parent_entity")
        hops += 1
    frappe.throw(_("That folder does not belong to this record"), frappe.PermissionError)


def _breadcrumbs(folder, root):
    trail, current = [], folder
    while current:
        trail.append({"name": current, "title": frappe.db.get_value("Drive File", current, "title")})
        if current == root:
            break
        current = frappe.db.get_value("Drive File", current, "parent_entity")
    return list(reversed(trail))


def _folder_row(folder):
    row = frappe.db.get_value(
        "Drive File", folder, ["name", "title", "team", "is_group", "file_size", "modified"], as_dict=True
    )
    if not row:
        return {"folder": None}
    row["folder"] = row.name
    row["open_url"] = f"/drive/{'d' if row.is_group else 'f'}/{row.name}"
    return base.serialize(row)
