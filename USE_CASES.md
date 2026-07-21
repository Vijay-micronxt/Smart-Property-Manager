# Smart Property Manager — Use Cases

> **Last updated:** 2026-07-21 — Phase 2 & 3: UC-17 Raise Maintenance Request, UC-18 Work Order, UC-19 Inspection Checklist, UC-20 Utility Billing, UC-21 Commission Rule, UC-22 Commission Entry, UC-23 Commission Settlement
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

## UC-13: Add Amenities to a Property

**Actor:** Property Manager
**Trigger:** Property listing needs to advertise its facilities.

**Steps:**
1. Open the Property record
2. Expand **Amenities** section
3. Click Add Row in the Amenities table
4. Enter Amenity name (e.g. "Swimming Pool"), Type (Recreation), optional Description
5. Repeat for each amenity
6. Save

**Outcome:** Amenities stored on the Property record, visible to Sales Users when pitching the property.

---

## UC-14: Attach Project Documents to a Property

**Actor:** Property Manager
**Trigger:** Legal or approval documents need to be stored against the project.

**Steps:**
1. Open the Property record
2. Expand **Project Documents** section
3. Click Add Row in the Documents table
4. Enter Document Name, Type (e.g. Title Deed), upload File, optionally set Expiry Date
5. Save

**Outcome:** Documents stored and linked to the property. Finance/Operations teams can access without leaving the form.

---

## UC-15: Renew a Lease

**Actor:** Property Manager
**Trigger:** A lease is approaching its end date and the tenant wishes to renew.

**Pre-condition:** Property Allocation is submitted with status Active and type Lease or Rental.

**Steps:**
1. Open the Property Allocation
2. Click Actions → **Renew Lease**
3. In the dialog:
   - Set **New End Date** (required)
   - Optionally enter **Rent Escalation (%)** (0 = keep current rent)
4. Click **Renew**

**Outcome:**
- `end_date` updated to the new date
- If escalation > 0: `rent_amount` updated accordingly (e.g. 10% → rent × 1.10)
- Success alert shown; form reloads with updated values
- Next billing cycle continues unchanged

**Error condition:** If allocation is not Active/submitted or is not Lease/Rental — error thrown and no change made.

---

## UC-16: Automatic Late Fee on Overdue Milestones

**Actor:** ERPNext System (scheduled daily job)
**Trigger:** Payment Plan milestone is unpaid beyond the grace period.

**Pre-condition:**
- `enable_late_fees` = checked in Property Core Settings
- `late_fee_percentage`, `late_fee_grace_days`, and `late_fee_item_code` configured

**Steps (automated):**
1. Daily billing engine runs
2. Queries Payment Plans where `payment_status = Pending`, `due_date < today - grace_days`, `late_fee_applied = 0`
3. Calculates `late_fee_amount = milestone_amount × late_fee_percentage / 100`
4. Creates a Sales Invoice for the late fee and links it to the milestone
5. Sets `late_fee_applied = 1`, `payment_status = Overdue`

**Outcome:** Overdue milestones automatically flagged; Finance team can collect the late fee via the linked Sales Invoice.

**Error condition:** If late fee Item not found — logged to Frappe Error Log per plan, others continue unaffected.

---

## UC-17: Raise a Maintenance Request

**Actor:** Tenant / Property Manager
**Trigger:** A unit has a fault or maintenance need.

**Steps:**
1. Go to Maintenance Request → New
2. Select Property Unit (customer auto-filled from unit)
3. Enter Subject, Description, Priority
4. Save

**Outcome:**
- Request created with status = Open
- Property Manager and Operations User can now assign it

---

## UC-18: Create a Work Order for Maintenance

**Actor:** Operations User / Property Manager
**Trigger:** Maintenance Request is received; work needs to be scheduled.

**Steps:**
1. Open a Maintenance Request
2. Click Actions → **Create Work Order**
3. New Work Order pre-fills property_unit and description
4. Add assigned_to or vendor, set scheduled_date → Save

**Outcome:**
- Work Order created and linked to Maintenance Request
- Maintenance Request status → Assigned
- As work progresses, update WO status (In Progress → Completed)
- On Completed: Maintenance Request status → Resolved

---

## UC-19: Run an Inspection Checklist

**Actor:** Operations User / Property Manager
**Trigger:** Tenant move-in, move-out, or periodic inspection.

**Steps:**
1. Go to Inspection Checklist → New
2. Select Property Unit, Inspection Type (e.g. Move-In), Inspection Date
3. Click Actions → **Load Default Items** (12 standard items pre-populated)
4. For each item, set Condition (OK / Minor Issue / Major Issue / N/A) and add Remarks
5. Set Overall Condition → Save → change status to Completed

**Outcome:**
- Inspection record stored permanently for the unit
- Evidence available for security deposit disputes

---

## UC-20: Record Utility Reading and Generate Bill

**Actor:** Operations User / Finance User
**Trigger:** Monthly meter reading is taken.

**Pre-condition:** Utility Meter set up for the unit with rate_per_unit and utility_item_code.

**Steps:**
1. Open the Utility Meter record → click Actions → **New Utility Bill**
2. Set billing_period_start, billing_period_end, previous_reading, current_reading
3. System calculates units_consumed and amount live
4. Save
5. Click Actions → **Generate Invoice**
6. Confirm dialog

**Outcome:**
- Sales Invoice created in ERPNext for the customer
- Utility Bill status → Invoiced
- Invoice linked on the bill record

---

## UC-21: Define a Commission Rule

**Actor:** Commission Manager / Property Manager
**Trigger:** Company sets up commission rates for sales agents.

**Steps:**
1. Go to Commission Rule → New
2. Enter Rule Name
3. Optionally select Property and/or Sales Person (blank = applies to all)
4. Select Commission Type (Percentage or Flat), enter Commission Rate
5. Optionally set Effective From / Effective To
6. Save

**Outcome:**
- Rule active and will apply to future bookings matching its scope

---

## UC-22: Auto-generate Commission Entry on Booking

**Actor:** ERPNext System (hook on Property Booking submit)
**Trigger:** Property Booking is submitted.

**Pre-condition:** At least one active Commission Rule exists matching the booking's property/sales person.

**Steps (automated):**
1. Booking is submitted
2. System finds highest-priority matching Commission Rule
3. Calculates commission_amount (booking_amount × rate% or flat amount)
4. Creates Commission Entry with status = Pending

**Outcome:**
- Commission Entry visible to Commission Manager and Sales User
- Ready to be included in a settlement batch

---

## UC-23: Settle Commission Payout

**Actor:** Commission Manager / Property Manager
**Trigger:** Period end; commissions due to a sales person need to be paid.

**Steps:**
1. Go to Commission Settlement → New
2. Select Sales Person, Settlement Date
3. Click Actions → **Load Pending Entries** (auto-fills child table from all Pending entries)
4. Review amounts; remove rows if needed
5. Save → review total_amount
6. Submit

**Outcome:**
- All included Commission Entries → status = Settled
- Finance team creates a Payment Entry to the sales person and links it in the `payment_entry` field
- On cancel: entries revert to Pending

---

## Future Use Cases (Not Yet Implemented)

| ID | Use Case | Notes |
|---|---|---|
| UC-24 | Tenant Portal — view invoices and submit requests | customer portal |
| UC-25 | Commission report by sales person and period | reporting |
