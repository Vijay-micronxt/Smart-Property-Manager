# Smart Property Manager — Use Cases

> **Last updated:** 2026-07-21 — added UC-12 Customer KYC
> Add a new use case whenever a new business workflow is implemented.

---

## Actors

| Actor | Role in System |
|---|---|
| Property Manager | Admin of properties, units, allocations, agreements |
| Sales User | Creates bookings, views units and pipeline |
| Finance User | Tracks invoices, payment plans, rent billing |
| Tenant / Buyer | End customer (no direct system access yet) |
| ERPNext System | Automated actor for scheduler jobs and accounting |

---

## UC-01: Register a New Property Project

**Actor:** Property Manager
**Trigger:** Company acquires or launches a new real estate project.

**Steps:**
1. Go to Property Core → Property → New
2. Enter property name, type (e.g. Apartment), company, status, launch date, total area, address
3. Optionally select a Payment Plan Template (milestone split for bookings)
4. Optionally mark the GIS location on the embedded map
5. Save

**Outcome:** Property record created. Property Units can now be added via "Add Unit" button or the Property Unit list.

---

## UC-02: Add Units to a Property

**Actor:** Property Manager
**Trigger:** Units need to be registered before they can be sold or leased.

**Steps:**
1. Open the Property → click "Add Unit" button (toolbar) OR go to Property Unit → New
2. Select the parent Property
3. Enter unit_number, unit_type, area, floor, facing, base_price
4. Set item_code (link to an ERPNext Item such as "Plot" or "Flat") — required before invoices can be generated
5. Optionally pin the unit location on the GIS map
6. Save

**Outcome:** Unit created with availability_status = Available.

**Validation:** Duplicate unit_number within the same Property is blocked.

---

## UC-03: Book a Unit (Sale Scenario)

**Actor:** Sales User
**Trigger:** A buyer expresses interest and pays a booking token amount.

**Pre-condition:** Unit availability_status = Available.

**Steps:**
1. Go to Property Booking → New
2. Select Customer (or create from CRM Lead/Opportunity)
3. Select Property Unit
4. Set booking_date, booking_amount, sales_person, and optionally link Opportunity
5. Save (validates unit is available)
6. Submit

**Outcome:**
- booking_status → Confirmed
- Unit availability_status → Booked
- Payment Plan records auto-created based on template or default split (10/20/20/25/25%)

**Error condition:** If unit is already Booked/Allocated — system throws "Property Unit is not available" and blocks submission.

---

## UC-04: Generate a Milestone Invoice

**Actor:** Finance User / Property Manager
**Trigger:** A payment milestone is due and an invoice needs to be sent to the customer.

**Pre-condition:** Property Booking is submitted. Payment Plan records exist. Unit has `item_code` set.

**Steps:**
1. Go to Payment Plan list → filter by Booking or open from booking dashboard
2. Open the milestone record (e.g. "On Foundation")
3. Click Actions → "Generate Invoice"
4. Confirm the dialog
5. System creates a Sales Invoice in ERPNext

**Outcome:**
- Payment Plan `invoice` field linked to new Sales Invoice
- `payment_status` → Invoiced
- Finance team can collect payment against the Sales Invoice in ERPNext

**Error condition:** If `item_code` is not set on the Property Unit — error message tells user exactly which Item to create and where.

---

## UC-05: Allocate a Unit (Sale Completion)

**Actor:** Property Manager
**Trigger:** All formalities are complete and the unit is formally transferred to the buyer.

**Pre-condition:** Property Booking confirmed. Agreement drafted.

**Steps:**
1. Go to Property Allocation → New
2. Set customer, property_unit, allocation_type = Sale, start_date
3. Link Property Booking and Property Agreement
4. Save → Submit

**Outcome:**
- Allocation status → Active
- Unit availability_status → Allocated
- Linked Property Agreement status → Active

---

## UC-06: Create a Lease Allocation with Recurring Billing

**Actor:** Property Manager
**Trigger:** A tenant signs a lease and recurring rent invoices must be generated monthly.

**Pre-condition:** Property Agreement created. `rent_item_code` configured in Property Core Settings.

**Steps:**
1. Go to Property Allocation → New
2. Set customer, property_unit, allocation_type = Lease
3. Set start_date, end_date (lease period)
4. In the Recurring Billing section:
   - Enter rent_amount (e.g. ₹25,000)
   - Set billing_frequency = Monthly
   - Set billing_day = 1 (invoice generated on 1st of each month)
5. Link Property Agreement
6. Save → Submit

**Outcome:**
- Unit status → Leased
- `next_billing_date` set to start_date with billing_day
- Each day, the billing engine checks and auto-generates a Sales Invoice when due
- Each generated invoice is logged in Rent Invoice Log

---

## UC-07: Record Security Deposit

**Actor:** Property Manager / Finance User
**Trigger:** Tenant pays security deposit at lease commencement.

**Pre-condition:** Property Agreement exists with `security_deposit_amount` filled. `security_deposit_account` configured in Property Core Settings.

**Steps:**
1. Open the Property Agreement
2. Set `security_deposit_amount` (if not already set), save
3. Click Deposit → "Record Security Deposit"
4. Confirm the dialog

**Outcome:**
- Journal Entry created:
  - Dr: Customer Receivable (tenant owes the deposit)
  - Cr: Security Deposit Account (liability — held until refund)
- `security_deposit_received` → checked
- `security_deposit_journal` linked on the agreement
- Finance team creates a Payment Entry against the JE to record actual cash receipt

---

## UC-08: Refund Security Deposit on Lease Termination

**Actor:** Property Manager
**Trigger:** Lease ends, tenant vacates, deposit is to be refunded.

**Pre-condition:** Property Agreement in Terminated status. Security deposit was previously recorded.

**Steps:**
1. Set agreement_status = Terminated, save
2. Click Deposit → "Refund Security Deposit"
3. Confirm the dialog
4. Go to ERPNext → Payment Entry → create outgoing payment to customer

**Outcome:**
- Deposit Journal Entry cancelled (liability reversed)
- Finance team processes the actual cash refund via Payment Entry

---

## UC-09: Configure Payment Plan Template

**Actor:** Property Manager
**Trigger:** Company uses a non-standard milestone split for a specific project type.

**Steps:**
1. Go to Payment Plan Template → New
2. Name the template (e.g. "Luxury Villa Split")
3. Add milestone rows:
   | Milestone | % | After (Months) |
   |---|---|---|
   | Token | 5 | 0 |
   | On Agreement | 15 | 1 |
   | On Approval | 20 | 3 |
   | On Completion | 60 | 18 |
4. Save (validates total = 100%)
5. Open the Property → set `payment_plan_template` = "Luxury Villa Split"

**Outcome:** All future bookings under this Property use the custom split.

---

## UC-10: View Rent Billing History

**Actor:** Finance User
**Trigger:** Need to audit which months have been invoiced for a lease.

**Steps:**
1. Open the Property Allocation record
2. Click View → "Rent Invoice Log"
3. List shows each billing cycle with period label, invoice link, and status

**Outcome:** Complete audit trail of auto-generated rent invoices.

---

## UC-11: Cancel a Booking

**Actor:** Property Manager / Sales User
**Trigger:** Buyer backs out before allocation.

**Pre-condition:** Property Booking is in submitted state.

**Steps:**
1. Open the Property Booking
2. Click Cancel

**Outcome:**
- booking_status → Cancelled
- Unit availability_status → Available (unit is released back to market)
- Existing Payment Plan records remain for audit but no new ones are created

---

## UC-12: Complete Customer KYC Screening

**Actor:** Property Manager / Sales User
**Trigger:** A new customer is created and must be KYC-verified before a booking or allocation is finalised.

**Steps:**
1. Go to CRM → Customer → open or create the customer record
2. Expand the **KYC & Verification** section
3. Fill:
   - ID Proof Type (e.g. Aadhaar)
   - ID Number
   - Upload ID Proof Document (scan/PDF)
4. Expand **Personal & Financial Details** section
5. Fill: Date of Birth, Nationality, Occupation, Annual Income, PAN Number, GST Number (if commercial), Address Proof Type, Address Proof Document
6. Click KYC → **Mark KYC Verified**
7. Confirm the dialog

**Outcome:**
- kyc_status = Verified
- kyc_verified_on = today, kyc_verified_by = current user
- Green banner shown on Customer form
- Customer is now cleared for booking/allocation

**Alternate flow — Reject:**
- Click KYC → **Reject KYC**
- kyc_status = Rejected; red banner shown; booking should not proceed

---

## Future Use Cases (Not Yet Implemented)

| ID | Use Case | App |
|---|---|---|
| UC-13 | Raise Maintenance Request | property_operations |
| UC-14 | Assign Work Order to Vendor | property_operations |
| UC-15 | Run Inspection Checklist | property_operations |
| UC-16 | Record Utility Meter Reading | property_operations |
| UC-17 | Define Commission Rule for Sales Person | property_commissions |
| UC-18 | Auto-generate Commission Entry on Booking | property_commissions |
| UC-19 | Settle Commission Payout | property_commissions |
| UC-20 | Tenant Portal — view invoices and submit requests | customer portal |
