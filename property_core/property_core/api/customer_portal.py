"""
Whitelisted APIs for a logged-in customer. Website users have no doctype
permissions, so every function here resolves and scopes to the calling
customer itself -- that resolution is the actual security boundary.
"""

import frappe
from frappe.utils import getdate, today, date_diff


def _get_customer_for_session():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(frappe._("Please login"))

    customer = frappe.db.get_value("Portal User", {"user": user, "parenttype": "Customer"}, "parent")
    if not customer:
        contact = frappe.db.get_value("Contact", {"email_id": user}, "name")
        if contact:
            customer = frappe.db.get_value(
                "Dynamic Link",
                {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
                "link_name",
            )
    if not customer:
        frappe.throw(frappe._("No customer account is linked to your login. Please contact our team."))

    return customer


def _assert_unit_belongs_to_customer(customer, property_unit):
    """Raise if the unit is not linked to this customer (booking or allocation)."""
    if not frappe.db.exists(
        "Property Booking",
        {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
    ) and not frappe.db.exists(
        "Property Allocation",
        {"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
    ) and not frappe.db.get_value(
        "Property Unit", property_unit, "customer"
    ) == customer:
        frappe.throw(frappe._("Selected unit does not belong to your account"))


# ─── Dashboard (existing) ─────────────────────────────────────────────────────

@frappe.whitelist()
def raise_issue(subject, description=None, property_unit=None):
    customer = _get_customer_for_session()

    subject = (subject or "").strip()
    if not subject:
        frappe.throw(frappe._("Subject is required"))

    if property_unit:
        _assert_unit_belongs_to_customer(customer, property_unit)

    issue = frappe.get_doc({
        "doctype": "Issue",
        "subject": subject,
        "description": description or subject,
        "raised_by": frappe.session.user,
        "customer": customer,
        "property_unit": property_unit or None,
    })
    issue.flags.ignore_permissions = True
    issue.insert(ignore_permissions=True)

    return {"ok": 1, "issue": issue.name}


@frappe.whitelist()
def customer_portal_get():
    customer = _get_customer_for_session()
    customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
    today_date = getdate(today())

    bookings = []
    for booking in frappe.get_all(
        "Property Booking",
        filters={"customer": customer, "docstatus": ["<", 2]},
        fields=["name", "property_unit", "booking_date", "booking_status", "booking_amount"],
        order_by="creation desc",
    ):
        plans = frappe.get_all(
            "Payment Plan",
            filters={"booking": booking.name},
            fields=["name", "milestone", "due_date", "amount", "payment_status", "invoice"],
            order_by="due_date asc",
        )
        for plan in plans:
            if plan.payment_status == "Paid":
                plan["status"] = "Paid"
            elif plan.due_date and getdate(plan.due_date) < today_date:
                plan["status"] = "Overdue"
            elif plan.due_date and date_diff(plan.due_date, today_date) <= 7:
                plan["status"] = "Due Soon"
            else:
                plan["status"] = "Upcoming"
            plan["due_date"] = str(plan.due_date) if plan.due_date else None

        bookings.append({
            "name": booking.name,
            "property_unit": booking.property_unit,
            "booking_date": str(booking.booking_date) if booking.booking_date else None,
            "booking_status": booking.booking_status,
            "booking_amount": booking.booking_amount,
            "payment_plan": plans,
        })

    units = frappe.get_all(
        "Property Unit",
        filters={"customer": customer},
        fields=["name", "property", "unit_number", "unit_type", "area", "base_price", "availability_status"],
    )

    agreements = frappe.get_all(
        "Property Agreement",
        filters={"customer": customer},
        fields=["name", "agreement_type", "agreement_status", "start_date", "end_date", "document_attachment"],
    )

    issues = frappe.get_all(
        "Issue",
        filters={"customer": customer},
        fields=["name", "subject", "status", "opening_date", "property_unit"],
        order_by="creation desc",
        limit_page_length=50,
    )

    return {
        "customer": {"name": customer, "customer_name": customer_name},
        "bookings": bookings,
        "units": units,
        "agreements": agreements,
        "issues": issues,
    }


# ─── Maintenance ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_maintenance_requests(property_unit=None, status=None, limit=50):
    """
    Returns the customer's Issues with their linked Work Order status.
    Optional filters: property_unit, status (Open/Replied/Resolved/Closed).
    """
    customer = _get_customer_for_session()

    filters = {"customer": customer}
    if property_unit:
        _assert_unit_belongs_to_customer(customer, property_unit)
        filters["property_unit"] = property_unit
    if status:
        filters["status"] = status

    issues = frappe.get_all(
        "Issue",
        filters=filters,
        fields=["name", "subject", "description", "status", "priority",
                "opening_date", "resolution_date", "property_unit"],
        order_by="creation desc",
        limit_page_length=int(limit),
    )

    for issue in issues:
        issue["opening_date"] = str(issue["opening_date"]) if issue["opening_date"] else None
        issue["resolution_date"] = str(issue["resolution_date"]) if issue["resolution_date"] else None

        work_orders = frappe.get_all(
            "Work Order",
            filters={"issue": issue["name"]},
            fields=["name", "status", "description", "assigned_to",
                    "scheduled_date", "completed_date", "estimated_cost", "actual_cost"],
        )
        for wo in work_orders:
            wo["scheduled_date"] = str(wo["scheduled_date"]) if wo["scheduled_date"] else None
            wo["completed_date"] = str(wo["completed_date"]) if wo["completed_date"] else None
        issue["work_orders"] = work_orders

    return {"issues": issues, "total": len(issues)}


# ─── Utility Bills ────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_utility_bills(property_unit=None, status=None, limit=50):
    """
    Returns utility bills for the customer's unit(s).
    Optional filters: property_unit, status (Unpaid/Paid/Overdue).
    """
    customer = _get_customer_for_session()

    filters = {"customer": customer}
    if property_unit:
        _assert_unit_belongs_to_customer(customer, property_unit)
        filters["property_unit"] = property_unit
    if status:
        filters["status"] = status

    bills = frappe.get_all(
        "Utility Bill",
        filters=filters,
        fields=["name", "property_unit", "status", "billing_period_start",
                "billing_period_end", "previous_reading", "current_reading",
                "units_consumed", "rate_per_unit", "amount", "invoice"],
        order_by="billing_period_start desc",
        limit_page_length=int(limit),
    )

    for bill in bills:
        bill["billing_period_start"] = str(bill["billing_period_start"]) if bill["billing_period_start"] else None
        bill["billing_period_end"] = str(bill["billing_period_end"]) if bill["billing_period_end"] else None

        meter = frappe.db.get_value(
            "Utility Meter",
            {"property_unit": bill["property_unit"]},
            ["meter_number", "utility_type", "unit_of_measure"],
            as_dict=True,
        )
        bill["meter"] = meter or {}

    return {"bills": bills, "total": len(bills)}


# ─── Outstanding Dues ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_outstanding_dues():
    """
    Returns all outstanding (unpaid/partially paid) Sales Invoices for the customer,
    oldest first, with a running total.
    """
    customer = _get_customer_for_session()

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"customer": customer, "docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "posting_date", "due_date", "grand_total",
                "outstanding_amount", "status", "remarks"],
        order_by="posting_date asc",
    )

    today_date = getdate(today())
    total_outstanding = 0.0
    total_overdue = 0.0

    for inv in invoices:
        inv["posting_date"] = str(inv["posting_date"]) if inv["posting_date"] else None
        inv["due_date"] = str(inv["due_date"]) if inv["due_date"] else None
        inv["is_overdue"] = bool(inv["due_date"] and getdate(inv["due_date"]) < today_date)
        total_outstanding += float(inv["outstanding_amount"] or 0)
        if inv["is_overdue"]:
            total_overdue += float(inv["outstanding_amount"] or 0)

    return {
        "invoices": invoices,
        "total_outstanding": total_outstanding,
        "total_overdue": total_overdue,
        "invoice_count": len(invoices),
    }


# ─── Payment History ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_payment_history(limit=50):
    """
    Returns submitted Payment Entries for the customer,
    newest first. Includes gateway reference (Razorpay/Mswipe) where available.
    """
    customer = _get_customer_for_session()

    payments = frappe.get_all(
        "Payment Entry",
        filters={"party_type": "Customer", "party": customer, "docstatus": 1},
        fields=["name", "posting_date", "mode_of_payment", "paid_amount",
                "reference_no", "reference_date", "remarks"],
        order_by="posting_date desc",
        limit_page_length=int(limit),
    )

    for pe in payments:
        pe["posting_date"] = str(pe["posting_date"]) if pe["posting_date"] else None
        pe["reference_date"] = str(pe["reference_date"]) if pe["reference_date"] else None

        # Attach invoice references
        pe["invoices"] = frappe.get_all(
            "Payment Entry Reference",
            filters={"parent": pe["name"], "reference_doctype": "Sales Invoice"},
            fields=["reference_name", "allocated_amount"],
        )

    # Also surface gateway-level tracking entries
    razorpay_logs = frappe.get_all(
        "Razorpay Payment Entry",
        filters={"customer": customer},
        fields=["name", "razorpay_order_id", "razorpay_payment_id",
                "amount", "currency", "status", "sales_invoice", "payment_entry"],
        order_by="creation desc",
        limit_page_length=int(limit),
    ) if frappe.db.exists("DocType", "Razorpay Payment Entry") else []

    mswipe_logs = frappe.get_all(
        "Mswipe Payment Entry",
        filters={"customer": customer},
        fields=["name", "mswipe_order_id", "mswipe_txn_id",
                "amount", "currency", "status", "sales_invoice", "payment_entry"],
        order_by="creation desc",
        limit_page_length=int(limit),
    ) if frappe.db.exists("DocType", "Mswipe Payment Entry") else []

    return {
        "payments": payments,
        "gateway_logs": {
            "razorpay": razorpay_logs,
            "mswipe": mswipe_logs,
        },
        "total": len(payments),
    }


# ─── Unit Details ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_unit_details(unit_name):
    """
    Returns full details for a specific Property Unit that belongs to the customer.
    Includes property info, allocation/agreement, and active payment plan.
    """
    customer = _get_customer_for_session()
    _assert_unit_belongs_to_customer(customer, unit_name)

    unit = frappe.get_doc("Property Unit", unit_name)
    property_doc = frappe.get_doc("Property", unit.property) if unit.property else None

    allocation = frappe.get_all(
        "Property Allocation",
        filters={"property_unit": unit_name, "customer": customer, "docstatus": ["<", 2]},
        fields=["name", "allocation_type", "status", "start_date", "end_date",
                "rent_amount", "billing_frequency", "next_billing_date"],
        order_by="creation desc",
        limit_page_length=1,
    )

    agreement = frappe.get_all(
        "Property Agreement",
        filters={"property_unit": unit_name, "customer": customer},
        fields=["name", "agreement_type", "agreement_status",
                "start_date", "end_date", "document_attachment"],
        order_by="creation desc",
        limit_page_length=1,
    )

    return {
        "unit": {
            "name": unit.name,
            "unit_number": unit.unit_number,
            "unit_type": unit.unit_type,
            "area": unit.area,
            "floor": unit.floor,
            "facing": unit.facing,
            "base_price": unit.base_price,
            "availability_status": unit.availability_status,
        },
        "property": {
            "name": property_doc.name if property_doc else None,
            "property_name": property_doc.property_name if property_doc else None,
            "property_type": property_doc.property_type if property_doc else None,
            "address": property_doc.address if property_doc else None,
            "amenities": [a.amenity_name for a in (property_doc.amenities or [])] if property_doc else [],
        },
        "allocation": allocation[0] if allocation else None,
        "agreement": agreement[0] if agreement else None,
    }


# ─── Inspection Reports ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_inspection_reports(property_unit=None, limit=20):
    """
    Returns inspection checklists for the customer's unit(s).
    """
    customer = _get_customer_for_session()

    if property_unit:
        _assert_unit_belongs_to_customer(customer, property_unit)
        unit_filter = property_unit
    else:
        # All units belonging to this customer
        units = frappe.get_all(
            "Property Unit", filters={"customer": customer}, pluck="name"
        )
        allocations = frappe.get_all(
            "Property Allocation",
            filters={"customer": customer, "docstatus": ["<", 2]},
            pluck="property_unit",
        )
        unit_filter = list(set(units + allocations))
        if not unit_filter:
            return {"inspections": [], "total": 0}

    filters = {"property_unit": ["in", unit_filter] if isinstance(unit_filter, list) else unit_filter}

    inspections = frappe.get_all(
        "Inspection Checklist",
        filters=filters,
        fields=["name", "property_unit", "inspection_type", "inspection_date",
                "status", "inspector", "overall_condition"],
        order_by="inspection_date desc",
        limit_page_length=int(limit),
    )

    for insp in inspections:
        insp["inspection_date"] = str(insp["inspection_date"]) if insp["inspection_date"] else None
        insp["items"] = frappe.get_all(
            "Inspection Checklist Item",
            filters={"parent": insp["name"]},
            fields=["item_name", "category", "condition", "remarks"],
        )

    return {"inspections": inspections, "total": len(inspections)}


# ─── Rent Invoice History ─────────────────────────────────────────────────────

@frappe.whitelist()
def get_rent_history(property_unit=None, limit=50):
    """
    Returns the rent billing history (Rent Invoice Log) for the customer's allocation(s).
    """
    customer = _get_customer_for_session()

    if property_unit:
        _assert_unit_belongs_to_customer(customer, property_unit)
        allocations = frappe.get_all(
            "Property Allocation",
            filters={"property_unit": property_unit, "customer": customer, "docstatus": ["<", 2]},
            pluck="name",
        )
    else:
        allocations = frappe.get_all(
            "Property Allocation",
            filters={"customer": customer, "docstatus": ["<", 2]},
            pluck="name",
        )

    if not allocations:
        return {"rent_history": [], "total": 0}

    logs = frappe.get_all(
        "Rent Invoice Log",
        filters={"allocation": ["in", allocations]},
        fields=["name", "allocation", "period_label", "period_start",
                "period_end", "invoice", "status", "error_log"],
        order_by="period_start desc",
        limit_page_length=int(limit),
    )

    for log in logs:
        log["period_start"] = str(log["period_start"]) if log["period_start"] else None
        log["period_end"] = str(log["period_end"]) if log["period_end"] else None

        if log["invoice"]:
            inv = frappe.db.get_value(
                "Sales Invoice", log["invoice"],
                ["grand_total", "outstanding_amount", "status"],
                as_dict=True,
            )
            log["invoice_details"] = inv or {}

    return {"rent_history": logs, "total": len(logs)}
