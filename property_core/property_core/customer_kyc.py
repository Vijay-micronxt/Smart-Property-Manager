"""
Custom fields added to ERPNext Customer DocType for KYC screening.
Defined here and imported in hooks.py via custom_fields.
Applied automatically on bench migrate — no ERPNext core modification.
"""

CUSTOMER_KYC_FIELDS = [
    # ── Section: KYC & Verification ──────────────────────────────────────
    {
        "fieldname": "property_kyc_section",
        "fieldtype": "Section Break",
        "label": "KYC & Verification",
        "insert_after": "website",
        "collapsible": 1,
    },
    {
        "fieldname": "kyc_status",
        "fieldtype": "Select",
        "label": "KYC Status",
        "options": "Pending\nVerified\nRejected",
        "default": "Pending",
        "insert_after": "property_kyc_section",
        "in_standard_filter": 1,
        "bold": 1,
    },
    {
        "fieldname": "kyc_verified_on",
        "fieldtype": "Date",
        "label": "Verified On",
        "insert_after": "kyc_status",
        "depends_on": "eval:doc.kyc_status === 'Verified'",
    },
    {
        "fieldname": "kyc_verified_by",
        "fieldtype": "Link",
        "label": "Verified By",
        "options": "User",
        "insert_after": "kyc_verified_on",
        "depends_on": "eval:doc.kyc_status === 'Verified'",
        "read_only": 1,
    },
    {
        "fieldname": "kyc_col_break_1",
        "fieldtype": "Column Break",
        "insert_after": "kyc_verified_by",
    },
    {
        "fieldname": "id_type",
        "fieldtype": "Select",
        "label": "ID Proof Type",
        "options": "\nAadhaar\nPAN Card\nPassport\nDriving Licence\nVoter ID",
        "insert_after": "kyc_col_break_1",
    },
    {
        "fieldname": "id_number",
        "fieldtype": "Data",
        "label": "ID Number",
        "insert_after": "id_type",
    },
    {
        "fieldname": "id_document",
        "fieldtype": "Attach",
        "label": "ID Proof Document",
        "insert_after": "id_number",
    },

    # ── Section: Personal & Financial Details ─────────────────────────────
    {
        "fieldname": "property_personal_section",
        "fieldtype": "Section Break",
        "label": "Personal & Financial Details",
        "insert_after": "id_document",
        "collapsible": 1,
    },
    {
        "fieldname": "date_of_birth",
        "fieldtype": "Date",
        "label": "Date of Birth",
        "insert_after": "property_personal_section",
    },
    {
        "fieldname": "nationality",
        "fieldtype": "Link",
        "label": "Nationality",
        "options": "Country",
        "insert_after": "date_of_birth",
    },
    {
        "fieldname": "occupation",
        "fieldtype": "Data",
        "label": "Occupation",
        "insert_after": "nationality",
    },
    {
        "fieldname": "annual_income",
        "fieldtype": "Currency",
        "label": "Annual Income",
        "insert_after": "occupation",
    },
    {
        "fieldname": "kyc_col_break_2",
        "fieldtype": "Column Break",
        "insert_after": "annual_income",
    },
    {
        "fieldname": "pan_number",
        "fieldtype": "Data",
        "label": "PAN Number",
        "insert_after": "kyc_col_break_2",
    },
    {
        "fieldname": "gst_number",
        "fieldtype": "Data",
        "label": "GST Number",
        "insert_after": "pan_number",
    },
    {
        "fieldname": "address_proof_type",
        "fieldtype": "Select",
        "label": "Address Proof Type",
        "options": "\nUtility Bill\nRent Agreement\nBank Statement\nPassport\nAadhaar",
        "insert_after": "gst_number",
    },
    {
        "fieldname": "address_proof_document",
        "fieldtype": "Attach",
        "label": "Address Proof Document",
        "insert_after": "address_proof_type",
    },
]


def sync_customer_kyc_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Customer": CUSTOMER_KYC_FIELDS}, ignore_validate=True, update=True)


def delete_customer_kyc_fields():
    """Runs on uninstall so ERPNext's Customer reverts cleanly -- these fields
    live on Customer (ERPNext-native), not a property_core doctype, so
    uninstalling this app doesn't remove them automatically."""
    import frappe

    frappe.db.delete(
        "Custom Field",
        {"dt": "Customer", "fieldname": ["in", [f["fieldname"] for f in CUSTOMER_KYC_FIELDS]]},
    )
