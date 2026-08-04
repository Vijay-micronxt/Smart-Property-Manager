# Smart Property Manager — Use Cases

> **Last updated:** 2026-08-04 — Customer Portal API v2 (`property_core.api.portal.*`): UC-48 bootstrap/dashboard, UC-49 unified charge feed, UC-50 maintenance charges, UC-51 maintenance work history + schedule, UC-52 ticket thread, UC-53 portal booking. UC-54 Property ↔ ERPNext Project link. See CUSTOMER_PORTAL_API.md.
> Previously: 2026-07-30 — Payment gateway integration: Razorpay order/capture/webhook (UC-34, UC-35), Mswipe order/callback (UC-36, UC-37), Paytm Pay-by-Link WhatsApp dealer dues (UC-38) + ecommerce checkout with partial payment (UC-39, UC-40). Customer report portal APIs: UC-41–UC-47 (maintenance, utility bills, outstanding dues, payment history, unit details, inspection reports, rent history). API authentication enforcement throughout.
> Previously: 2026-07-23 (part 2) — Architecture unification: retired Maintenance Request entirely, Issue is now the single complaint/query entry point (UC-17 revised), Work Order links to Issue directly (UC-18 revised). Added recurring maintenance billing (UC-32, UC-33), ported from JD's proven live pattern.
> Previously same day — JD BRD gap-closing pass: UC-26 CRM↔Property link, UC-27 Raise Issue (portal API), UC-28 Customer Portal data API, UC-29 Automatic Payment Plan invoicing. Also fixed 12 bugs found while installing/testing all 3 apps (see BUGS_AND_FIXES.md) and closed against JD's BRD (see BRD_GAP_ANALYSIS.md).
> Previously: 2026-07-21 — Phase 2 & 3: UC-19 Inspection Checklist, UC-20 Utility Billing, UC-21 Commission Rule, UC-22 Commission Entry, UC-23 Commission Settlement
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

## UC-17: Raise a Complaint or Query (Issue)

**Actor:** Tenant / Customer (via portal API) / Property Manager
**Trigger:** A unit has a fault, or the customer has any query/complaint.

> **Revised 2026-07-23:** there is no separate "Maintenance Request" doctype anymore — `Issue` (ERPNext's native ticketing doctype, already used for general queries) is now the single entry point for anything a customer or tenant raises, maintenance-related or not. This matches how JD's own live site works — it never had a separate Maintenance Request either.

**Steps (Desk):**
1. Go to Issue → New
2. Select Customer, set Property Unit (optional but recommended)
3. Enter Subject, Description, Priority
4. Save

**Steps (Portal API):** logged-in customer calls `property_core.property_core.api.customer_portal.raise_issue(subject, description, property_unit)` — see UC-27.

**Outcome:**
- Issue created with status = Open
- Property Manager / Operations User can now dispatch a Work Order against it if it needs physical work (UC-18)

---

## UC-18: Create a Work Order to Resolve an Issue

**Actor:** Operations User / Property Manager
**Trigger:** An Issue needs a technician/vendor visit, not just a reply.

**Steps:**
1. Open the Issue
2. Click Actions → **Create Work Order**
3. New Work Order pre-fills `issue` and `property_unit`
4. Add assigned_to or vendor, set scheduled_date → Save

**Outcome:**
- Work Order created, linked back to the Issue (`Issue.work_order` set)
- As work progresses, update the Work Order's own status (Assigned → In Progress → Completed) — Work Order tracks this granularity itself, it isn't mirrored onto the Issue
- On Completed: Issue status → Resolved, `resolution_details` filled from the Work Order's description

**Note:** the `issue` link on Work Order is optional — internal/preventive work with no customer complaint behind it can still create a standalone Work Order.

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

## UC-26: Link a CRM Opportunity to a Property/Unit

**Actor:** Sales User
**Trigger:** A lead progresses to an Opportunity and the prospect's property interest is known.

**Steps:**
1. Open (or convert to) an Opportunity
2. Expand the **Property Interest** section
3. Set Property, and optionally the specific Property Unit
4. Save

**Outcome:**
- The Opportunity now carries which Property/Unit the prospect is interested in, from first contact onward — no longer only recorded once an actual Booking exists
- Property's Connections show an "Opportunities" link back to every Opportunity raised against it

---

## UC-27: Customer Raises a Support Ticket (Portal API)

**Actor:** Customer (via portal login)
**Trigger:** Customer has a query or complaint about their unit.

**Pre-condition:** Customer has portal access (see UC-28's provisioning note) and, if linking a unit, owns a Booking or Allocation against it.

**Steps (API-level — no portal page yet, see Deferred below):**
1. Logged-in customer calls `property_core.property_core.api.customer_portal.raise_issue(subject, description, property_unit)`

**Outcome:**
- An ERPNext **Issue** is created (`customer`, `property_unit` set), visible to staff in the standard Issue list
- If `property_unit` is supplied but doesn't belong to the caller (no matching Booking/Allocation), the call is rejected: "Selected unit does not belong to your account"

**Note:** this is the data/API layer only. The actual customer-facing raise-a-ticket page is deferred to the portal-UI pass.

---

## UC-28: Customer Views Their Own Bookings & Payment Status (Portal API)

**Actor:** Customer (via portal login)
**Trigger:** Customer wants to check what they've booked and what they owe.

**Pre-condition:** Customer has portal access.

**Steps (API-level — no portal page yet):**
1. Logged-in customer calls `property_core.property_core.api.customer_portal.customer_portal_get()`

**Outcome:** Returns, scoped strictly to that customer:
- Their Property Bookings, each with its Payment Plan rows labelled Paid / Overdue / Due Soon / Upcoming
- Their Property Units, Property Agreements, and Issues

**Related — how portal access is granted:** submitting a Property Booking now auto-provisions portal access for the customer if they don't already have it (Website User + Portal User, email sourced from the Customer's primary Contact) — mirrors how JD's live site does it, wrapped so a missing contact email never blocks the booking itself.

**Note:** API/data layer only — no portal web page yet (deferred to its own pass).

---

## UC-29: Automatic Invoice Generation for Payment Plan Milestones

**Actor:** ERPNext System (scheduled daily job)
**Trigger:** A Payment Plan milestone's due date arrives.

**Steps (automated):**
1. Daily scheduler (`payment_plan_billing.run_daily_payment_plan_billing`) runs
2. Finds Payment Plan rows where `payment_status = Pending`, `due_date <= today`, and no invoice yet
3. Calls the milestone's own `generate_invoice()` (same method the manual "Generate Invoice" button uses)

**Outcome:**
- The Sale side now gets the same automatic invoicing the Lease/Rent side already had via `billing_engine.py` — no more manual button-click required for a milestone that's come due
- Milestones not yet due are left untouched

**Note:** deliberately has no reminder/notification logic — that's left for the branch owner to wire via Server Script separately, so message templates can change without redeploying app code.

---

## UC-32: Configure a Recurring Maintenance Plan for a Unit

**Actor:** Operations User / Property Manager
**Trigger:** A unit needs a recurring monthly society/upkeep charge, independent of any complaint.

**Steps:**
1. Go to Maintenance Plan Template → New
2. Name the template, add month-wise charge rows (`month_no` + `amount`), or a `fixed_due_date` row for a one-off charge on a specific date
3. Optionally set `Repeat Every N Months` + `Repeat Amount` so billing continues indefinitely after the listed months run out (0 = stop)
4. Save
5. Open the Property Unit → set `Maintenance Plan Template` + `Maintenance Start Date`
6. Ensure `Maintenance Item Code` is set once in Property Core Settings

**Outcome:** the unit is now enrolled in recurring maintenance billing (see UC-33).

---

## UC-33: Automatic Recurring Maintenance Invoicing

**Actor:** ERPNext System (scheduled daily job)
**Trigger:** A unit's maintenance schedule has a period due.

**Pre-condition:** Property Unit has a Maintenance Plan Template + Start Date, `Pause Maintenance Billing` is unchecked, and `Maintenance Item Code` is configured in Property Core Settings.

**Steps (automated):**
1. Daily scheduler (`maintenance_billing.run_daily_maintenance_billing`) runs
2. For each enrolled, non-paused unit, works out which billing periods (by month number, or a repeat rule after the listed months) have a due date on or before today
3. Skips any period already invoiced (tracked via `Sales Invoice.maintenance_period`)
4. Creates + submits one Sales Invoice per newly-due period

**Outcome:** recurring maintenance charges are billed automatically, same automation level as the Lease/Rent (`billing_engine.py`) and Sale-side Payment Plan (`payment_plan_billing.py`) billing. No reminder/notification logic here either — same standing decision as UC-29.

**Ported from:** JD's own live, proven `Plot Maintenance - Generate Invoices & Remind` pattern (month-wise schedule + repeat rule), confirmed via the JD site audit — minus its WhatsApp half.

---

## UC-34: Initiate a Razorpay Payment (Order or Payment Link)

**Actor:** Sales User / Frontend application (authenticated API call)
**Trigger:** Customer needs to pay for a booking milestone, utility bill, or invoice via Razorpay.

**Pre-condition:** Razorpay Settings configured (`api_key`, `api_secret`). `bench migrate` run so doctype exists in DB. Caller authenticated via `Authorization: token api_key:api_secret` header.

**API:** `property_core.property_core.api.ecommerce.razorpay_integration.order_payment`

**Steps:**
1. Frontend calls `order_payment(amount, customer, order_id, currency="INR")` with amount in **paise**
2. Gateway creates a Razorpay order via API (amount passed through as-is — no ×100 conversion)
3. Razorpay Transaction Log record created for audit
4. Razorpay Payment Entry record created (amount stored in rupees = paise ÷ 100)
5. API returns `razorpay_order_id` and `amount` to the frontend
6. Frontend opens Razorpay checkout modal using the returned `razorpay_order_id`

**Alternate flow — Payment Link:**
- Call `create_payment_link(amount, customer, description)` to generate a hosted payment page URL instead of a modal

**Outcome:** Razorpay order created. Transaction Log and Payment Entry tracking records created. Customer completes payment via Razorpay checkout or hosted link.

**Security:** `allow_guest=True` removed — endpoint requires a valid ERPNext API token. Guest calls receive `PermissionError: Function is not whitelisted`.

**Amount convention:** always pass paise. Examples: ₹460 → `46000`, ₹10,000 → `1000000`.

---

## UC-35: Process Razorpay Payment Webhook (payment.captured)

**Actor:** ERPNext System (webhook from Razorpay)
**Trigger:** Razorpay fires a `payment.captured` event after the customer completes payment.

**Pre-condition:** Razorpay webhook URL registered in Razorpay Dashboard pointing to `/api/method/property_core.property_core.api.ecommerce.razorpay_webhooks.handle_razorpay_webhook`. Optionally `webhook_secret` set in Razorpay Settings for HMAC verification.

**Steps (automated):**
1. Razorpay POSTs event JSON to the webhook endpoint
2. If `webhook_secret` configured: HMAC-SHA256 signature verified; mismatch → logged and rejected
3. `_handle_payment_captured()` runs:
   a. Looks up Razorpay Payment Entry by `razorpay_order_id`
   b. If `sales_invoice` not yet on the entry: looks up original SO name from Razorpay Transaction Log, calls `create_sales_invoice_from_order()` to create a submitted Sales Invoice
   c. Sets `rpe.sales_invoice` to the new SI
   d. Calls `create_payment_entry_from_razorpay(rpe)` to create and submit a Payment Entry allocated to the SI
   e. Marks RPE `status = CAPTURED`

**Outcome:** Sales Invoice + Payment Entry created in ERPNext. RPE linked to both. Finance team can see the received payment immediately.

**Idempotency:** if the webhook fires twice for the same order, the second call finds `rpe.payment_entry` already set and skips PE creation.

---

## UC-36: Initiate a Mswipe Payment

**Actor:** Sales User / Frontend application (authenticated API call)
**Trigger:** Customer needs to pay via Mswipe hosted payment page.

**Pre-condition:** Mswipe Settings configured (`user_id`, `password`, `client_id`, `cust_code`). Caller authenticated.

**API:** `property_core.property_core.api.ecommerce.mswipe_integration.order_payment`

**Steps:**
1. Authenticated call with `amount`, `customer`, `order_id`, `return_url`
2. Mswipe API called to create a transaction
3. Mswipe Payment Entry tracking record created
4. Redirect URL returned to the frontend
5. Frontend redirects the customer's browser to the Mswipe hosted payment page

**Outcome:** Mswipe transaction initiated. Customer completes payment on Mswipe's page and is redirected back via `return_url`.

**Security:** same as Razorpay — `@frappe.whitelist()` only, requires ERPNext API token.

---

## UC-37: Process Mswipe Payment Callback

**Actor:** ERPNext System (callback from Mswipe)
**Trigger:** Mswipe redirects the customer's browser (or posts a server-side callback) to the callback URL after payment.

**Pre-condition:** Mswipe Settings configured.

**Steps (automated):**
1. Mswipe POSTs/redirects to `/api/method/...handle_mswipe_callback` with `encIpgId` (transaction ID)
2. Transaction looked up by `trans_id` in cache or Mswipe Payment Entry
3. **Server-to-server status check** performed via `gateway.check_transaction_status(trans_id)` — callback parameters never trusted alone
4. If `Payment_Status != 1` (success): Mswipe Payment Entry status set to FAILED/PENDING; redirect to `return_url?status=TXN_FAILURE`
5. If successful:
   - Idempotency guard: check if PE already linked on entry, or PE with matching `reference_no` already submitted
   - `create_sales_invoice_from_order(order_id)` creates submitted SI
   - Mswipe Payment Entry updated (customer, txn_id, amount, status=SUCCESS)
   - `create_payment_entry_from_mswipe()` creates and submits Payment Entry
   - Single `frappe.db.commit()` at end
6. Browser redirected to `return_url?status=TXN_SUCCESS`

**Outcome:** SI + PE created. Customer lands on success page. Finance sees received payment.

---

## UC-38: Generate Paytm Payment Link for WhatsApp (Dealer Dues)

**Actor:** WhatsApp automation / external integration (guest endpoint)
**Trigger:** Customer contacts via WhatsApp to pay outstanding dues; automation calls the API with the customer's phone number.

**Pre-condition:** Paytm Settings configured (`merchant_id`, `merchant_key`). Customer has outstanding Sales Invoices.

**API:** `property_core.property_core.api.paytm_payment_link.generate_payment_link` (allow_guest=True)

**Steps:**
1. External system POSTs `{"phone": "9876543210"}` to the endpoint
2. Last 10 digits extracted; customer looked up by mobile_no or via Contact Phone
3. Outstanding Sales Invoices summed → `total_due`
4. Paytm order created with `linkType = PARTIAL` (dealer always pays any portion they can)
5. Order details cached (`paytm_order:{order_id}`) for 7 days
6. Paytm payment link URL returned along with a pre-formatted WhatsApp message

**Outcome:** Customer receives a payment link via WhatsApp. Any partial payment is accepted.

**Error cases:** No customer found for phone → `{"status": "error", "message": "No customer found for phone ending in ..."}`. No outstanding dues → `{"status": "ok", "amount": 0, "message": "No outstanding dues"}`.

---

## UC-39: Generate Paytm Ecommerce Payment Link (with Optional Partial Payment)

**Actor:** Sales User / Frontend application (authenticated)
**Trigger:** Customer needs to pay for a Sales Order (booking instalment or full amount) via Paytm.

**Pre-condition:** Paytm Settings configured. Sales Order submitted and not fully billed. Caller authenticated.

**API:** `property_core.property_core.api.paytm_payment_link.generate_ecommerce_payment_link`

**Steps:**
1. Authenticated call with `so_name`, optional `amount` (instalment), optional `allow_partial=1`, optional `min_partial_amount`
2. `amount` defaults to SO `grand_total` if not provided
3. Validation: `amount` must be > 0 and ≤ SO `grand_total`
4. If `allow_partial=1`: Paytm link created with `linkType = PARTIAL`; if `min_partial_amount` provided, `minPaymentAmount` set (floor for partial payment)
5. If `allow_partial=0` (default): `linkType = FIXED` — customer must pay exact amount
6. Order details cached for 7 days
7. Returns `{"link": "...", "amount": ..., "order_id": "...", "message": "..."}` — `message` is a pre-formatted WhatsApp-ready string

**Outcome:** Customer pays full or partial amount via Paytm link. Webhook handles SI+PE creation after payment.

**Partial payment example:**
```
POST /api/method/property_core.property_core.api.paytm_payment_link.generate_ecommerce_payment_link
Authorization: token api_key:api_secret
Content-Type: application/json

{
  "so_name": "SAL-ORD-2026-00001",
  "amount": 100000,
  "allow_partial": 1,
  "min_partial_amount": 25000
}
```
Customer can pay any amount ≥ ₹25,000.

---

## UC-40: Process Paytm Payment Webhook

**Actor:** ERPNext System (webhook from Paytm)
**Trigger:** Paytm calls the callback URL after the customer completes (or abandons) a payment.

**Pre-condition:** Paytm Settings configured. Order cached in Redis.

**Steps (automated):**
1. Paytm POSTs to `/api/method/...handle_link_payment` with `body.orderId`
2. If `head.signature` present: AES-CBC signature verified; mismatch → logged and rejected
3. **Server-to-server order status** confirmed via Paytm API (`/v3/order/status`) — callback never trusted alone
4. If `resultStatus != TXN_SUCCESS`: return `{"status": "pending"}`
5. Idempotency check: if PE already exists with this `txn_id` → return `{"status": "ok", "reason": "already_processed"}`
6. Cached order retrieved from Redis; `flow` field determines handler:
   - `ecommerce` flow: create SI from SO, then create PE allocated to SI
   - `dealer_dues` flow: create PE allocated across outstanding invoices oldest-first
7. Always returns HTTP 200 (Paytm retries on non-200, causing duplicate PEs)

**Outcome:** SI + PE created. Order processing result logged to Frappe Error Log (success level) for audit.

---

## UC-41: Customer Views Their Maintenance Requests (Portal API)

**Actor:** Customer (portal login)
**Trigger:** Customer wants to see their filed complaints and their resolution status.

**API:** `property_core.property_core.api.customer_portal.get_maintenance_requests`

**Steps:**
1. Logged-in customer calls `get_maintenance_requests(property_unit?, status?, limit=50)`
2. System resolves customer from session — never trusts a `customer` parameter
3. If `property_unit` provided: ownership verified; unowned unit → error
4. Returns Issues with linked Work Orders (scheduled date, completion date, estimated/actual cost)

**Outcome:** Customer sees all their raised issues (with optional filters) and the dispatch/resolution status of each.

---

## UC-42: Customer Views Utility Bills (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_utility_bills`

**Steps:** Call `get_utility_bills(property_unit?, status?, limit=50)`.

**Outcome:** Returns utility bills for the customer's unit(s), each enriched with meter info (meter_number, utility_type, unit_of_measure). Optional filters: `property_unit`, `status` (Unpaid/Paid/Overdue).

---

## UC-43: Customer Views Outstanding Dues (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_outstanding_dues`

**Steps:** Call `get_outstanding_dues()`.

**Outcome:** Returns all submitted Sales Invoices with `outstanding_amount > 0`, each tagged `is_overdue` if past due date. Response includes `total_outstanding` and `total_overdue` summary totals. Invoices ordered oldest-first (same order as auto-allocation in payment processing).

---

## UC-44: Customer Views Payment History (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_payment_history`

**Steps:** Call `get_payment_history(limit=50)`.

**Outcome:** Returns submitted Payment Entries (newest first) with allocated invoice references. Also surfaces gateway-level tracking entries from `Razorpay Payment Entry` and `Mswipe Payment Entry` if those doctypes exist, giving the customer full visibility into gateway reference numbers (Razorpay order/payment IDs, Mswipe transaction IDs).

---

## UC-45: Customer Views Unit Details (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_unit_details`

**Steps:** Call `get_unit_details(unit_name)`.

**Pre-condition:** Unit must be owned by the calling customer (Booking or Allocation or direct `customer` field).

**Outcome:** Returns unit fields (number, type, area, floor, facing, price, status), parent property details (name, type, address, amenities list), and the customer's active Allocation and Agreement for that unit. Unowned units → "Selected unit does not belong to your account".

---

## UC-46: Customer Views Inspection Reports (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_inspection_reports`

**Steps:** Call `get_inspection_reports(property_unit?, limit=20)`.

**Outcome:** Returns Inspection Checklists for the customer's unit(s) (move-in, move-out, periodic), each with its checklist item detail rows (item_name, category, condition, remarks). If no `property_unit` filter: returns reports across all units owned via `Property Unit.customer` or active Allocations.

---

## UC-47: Customer Views Rent Invoice History (Portal API)

**Actor:** Customer (portal login)
**API:** `property_core.property_core.api.customer_portal.get_rent_history`

**Steps:** Call `get_rent_history(property_unit?, limit=50)`.

**Outcome:** Returns Rent Invoice Log entries for the customer's active Allocations, newest-first. Each log row includes `period_label`, `period_start`, `period_end`, `status`, and if an invoice exists: the linked SI's `grand_total`, `outstanding_amount`, and `status` inline. Customer can see which months are billed, paid, or outstanding.

---

## UC-48: Customer Portal Bootstrap and Home Screen (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.meta.settings`, `property_core.api.portal.profile.me`, `property_core.api.portal.dashboard.summary`

**Steps:**
1. Client calls `meta.settings` once at startup.
2. Client calls `dashboard.summary` for the landing screen.

**Outcome:** `settings` returns currency, status colours, every Select option list (unit status/type, booking status, issue status), charge types and feature flags, so no label or colour is hardcoded in the frontend. `dashboard.summary` returns totals (units, bookings, outstanding, overdue, open issues, open work orders), a per-charge-type breakdown, the single `next_due` charge, and the five most recent bookings, payments, work orders and open issues. One call fills a home screen; every section has a dedicated endpoint for its own tab.

---

## UC-49: Customer Views All Charges in One Feed (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.billing.charges`

**Steps:** Call `charges(property_unit?, charge_type?, status?, limit=200)`.

**Outcome:** Booking milestones, recurring maintenance invoices, rent invoices and un-invoiced utility bills are merged into one list, each row tagged with `charge_type` and carrying the same `amount` / `outstanding` / `due_date` / `status` shape. Status is computed identically for every type: `Paid` when nothing is outstanding, else `Overdue` / `Due Soon` (7 days) / `Upcoming`. Returns `totals` and a `by_type` breakdown alongside the rows, so a Payments tab needs exactly one request.

---

## UC-50: Customer Views Recurring Maintenance Charges (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.billing.maintenance_charges`

**Steps:** Call `maintenance_charges(property_unit?, status?, limit=60)`.

**Outcome:** Returns the Sales Invoices raised by the daily maintenance billing job — identified by the `maintenance_period` stamp — newest period first, with per-row status, `total_due` and `total_billed`. This is the charge side of maintenance; UC-51 is the work side.

---

## UC-51: Customer Sees What Maintenance Work Was Done (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.maintenance.work_history`, `property_core.api.portal.maintenance.schedule`

**Steps:**
1. Call `work_history(property_unit?, status?, limit=100)` for the work trail.
2. Call `schedule(property_unit?)` for what is due next.

**Outcome:** `work_history` returns every Work Order on the customer's units — description, scheduled and completed dates, actual cost, notes, and the complaint it came from — plus a summary (completed, open, total cost, counts by status). `schedule` reads the unit's Maintenance Plan Template and returns upcoming scheduled rows and the repeat cycle, with `due_date` derived from `maintenance_start_date + month_no`, and `billed: 1` on periods already invoiced.

---

## UC-52: Customer Tracks and Replies on a Ticket (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.support.issues`, `.issue`, `.raise_issue`, `.add_comment`

**Steps:**
1. `raise_issue(subject, description?, property_unit?, priority?)` opens the ticket.
2. `issues(property_unit?, status?, limit=50)` lists them with the Work Orders raised against each.
3. `issue(issue)` opens one with its full comment thread.
4. `add_comment(issue, message)` posts the customer's reply.

**Outcome:** A two-way support thread without desk access. The unit, when passed, must belong to the customer; a foreign issue name is rejected with `Issue X does not belong to your account`.

---

## UC-53: Customer Books a Unit From the Portal (Portal API v2)

**Actor:** Customer (portal login)
**API:** `property_core.api.portal.properties.available_units`, `property_core.api.portal.properties.site_map`, `property_core.api.portal.bookings.book_unit`

**Steps:**
1. Browse `available_units(property?, unit_type?)` or the map via `site_map(property?)`.
2. Call `book_unit(property_unit, note?)`.

**Outcome:** A **draft** Property Booking is created with the price read server-side from the unit, and a high-priority ToDo is raised for every enabled Property Manager. The client cannot influence rate or area. Guards run in order: unit exists → status is `Available` → no other live booking on it. On the map, other customers' identities are never exposed — only status and a `mine` flag.

---

## UC-54: Link a Property to an ERPNext Project

**Actor:** Property Manager
**Trigger:** The development is tracked as a Project (tasks, progress, costing) alongside its Property record.

**Steps:**
1. Create or open the Project in ERPNext.
2. Open Property Core → Property → set **Project**.
3. Save units/bookings under it (or let them fetch on next save).

**Outcome:** `Property.project` flows down as a read-only fetched field on Property Unit, Property Booking, Property Allocation and Property Agreement, and is returned by every portal endpoint that mentions a unit. Bookings created before the field existed resolve their project from the unit at read time. The link is manual by design — no Project is auto-created.

---

## Future Use Cases (Not Yet Implemented)

| ID | Use Case | Notes |
|---|---|---|
| UC-24 | Tenant Portal — web pages for invoices and requests | Full API surface implemented (UC-27/28, UC-41–47 legacy; UC-48–53 `api.portal.*`); a bundled `/customer-portal` page exists, a richer customer-facing UI is still open |
| UC-25 | Commission report by sales person and period | reporting |
| UC-30 | WhatsApp/SMS notifications (payment reminders, follow-ups) | explicitly deferred — to be wired via Server Script, not app code |
| UC-31 | Lead assignment rules (round-robin, auto-apply salesperson) | raised as a feature-flag-gated configuration item, not yet scoped |
