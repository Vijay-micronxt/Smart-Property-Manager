# Smart Property Manager — Test Cases

> **Last updated:** 2026-07-23 (part 2) — Retired TC-MR-* (Maintenance Request deleted entirely); added TC-IWO (Issue↔Work Order, unified) and TC-MPT (Maintenance Plan Template recurring billing).
> Previously same day — JD BRD gap-closing pass: added TC-CRM (Opportunity↔Property link), TC-CP (Customer Portal API), TC-PPB (automatic Payment Plan invoicing). Also fixed 12 bugs found while installing/testing all 3 apps (see BUGS_AND_FIXES.md).
> Previously: 2026-07-21 — Phase 1: added TC-AM (amenities), TC-PD (project documents), TC-LR (lease renewal), TC-LF (late fees), TC-RO (role permissions)
> Add test cases for every new feature. Mark status after each test run.
> Status: ✅ Pass | ❌ Fail | ⏭ Skip | 🔄 In Progress

---

## How to Run Tests

**Automated (unit tests):**
```bash
bench --site your-site.com run-tests --app property_core
```

**Manual (UI tests):**
Follow steps in each test case on a dev/staging ERPNext instance with property_core installed.

**Trigger billing engine manually:**
```bash
bench --site your-site.com execute property_core.property_core.utils.billing_engine.run_daily_billing
```

---

## Pre-conditions for All Tests

Before running any test:
- [ ] property_core app installed and migrated
- [ ] At least one Company exists in ERPNext
- [ ] Property Core Settings configured: Default Company, Security Deposit Account, Rent Item Code
- [ ] ERPNext Items exist: at least one matching a unit_type (e.g. "Flat") and one for rent (e.g. "Monthly Rent")

---

## Module: Property

### TC-P-01 — Create Property (Happy Path)
| | |
|---|---|
| **Use Case** | UC-01 |
| **Steps** | 1. New Property → fill property_name="Test Towers", property_type="Apartment", company, status="Active" → Save |
| **Expected** | Record saved. Name = "Test Towers". |
| **Status** | ⏭ |

### TC-P-02 — Property with GIS Location
| | |
|---|---|
| **Steps** | Open Property → expand GIS Location section → pin a location on the map → Save |
| **Expected** | geo_location field stores coordinate data. Map renders pinned location on re-open. |
| **Status** | ⏭ |

### TC-P-03 — GIS Section Collapsed by Default
| | |
|---|---|
| **Steps** | Open any Property form |
| **Expected** | "GIS Location" section is collapsed. Main fields (name, type, status) visible without scrolling. |
| **Status** | ⏭ |

### TC-P-04 — Add Unit Button
| | |
|---|---|
| **Steps** | Open a saved Property → click Create → "Add Unit" |
| **Expected** | New Property Unit form opens with `property` pre-filled. |
| **Status** | ⏭ |

### TC-P-05 — Units Connection Count
| | |
|---|---|
| **Steps** | Create 3 Property Units linked to a Property → open the Property form |
| **Expected** | "Property Units 3" connection shown at top of form. Click navigates to filtered unit list. |
| **Status** | ⏭ |

---

## Module: Property Unit

### TC-U-01 — Create Unit (Happy Path)
| | |
|---|---|
| **Use Case** | UC-02 |
| **Steps** | New Property Unit → property, unit_number="101", unit_type="Flat", base_price=1000000 → Save |
| **Expected** | Unit saved. availability_status = "Available". |
| **Status** | ⏭ |

### TC-U-02 — Duplicate Unit Number Blocked
| | |
|---|---|
| **Steps** | Create two Property Units with the same property and unit_number |
| **Expected** | Second save throws: "Unit Number X already exists for Property Y" |
| **Status** | ⏭ |

### TC-U-03 — Item Code Warning
| | |
|---|---|
| **Steps** | Open a Property Unit where item_code is blank |
| **Expected** | Warning message visible in the item_code field description prompting user to set it. |
| **Status** | ⏭ |

### TC-U-04 — New Booking Button
| | |
|---|---|
| **Steps** | Open a saved Property Unit → click Create → "New Booking" |
| **Expected** | New Property Booking form opens with property_unit pre-filled. |
| **Status** | ⏭ |

### TC-U-05 — Availability Status Indicator
| | |
|---|---|
| **Steps** | Open a Property Unit with availability_status = "Available" |
| **Expected** | Green intro banner: "This unit is available for booking." |
| **Status** | ⏭ |

---

## Module: Property Booking

### TC-B-01 — Create and Submit Booking (Happy Path)
| | |
|---|---|
| **Use Case** | UC-03 |
| **Steps** | New Booking → Customer, Property Unit (Available), booking_amount=50000 → Save → Submit |
| **Expected** | booking_status = "Confirmed". Unit availability_status = "Booked". Payment Plan records created. |
| **Status** | ⏭ |

### TC-B-02 — Double Booking Blocked
| | |
|---|---|
| **Steps** | Submit a booking for Unit A. Create another booking for the same Unit A → attempt Submit |
| **Expected** | Error: "Property Unit X is not available. Current status: Booked" |
| **Status** | ⏭ |

### TC-B-03 — Double Booking Blocked at Save
| | |
|---|---|
| **Steps** | Submit booking 1 for Unit A. Create booking 2 for same Unit A → Save (before submit) |
| **Expected** | Error thrown at validate: unit not available. |
| **Status** | ⏭ |

### TC-B-04 — Payment Plan Auto-Generated with Default Split
| | |
|---|---|
| **Pre-condition** | Property has no payment_plan_template. Unit base_price = 1,000,000. |
| **Steps** | Submit a booking |
| **Expected** | 5 Payment Plan records: 100k / 200k / 200k / 250k / 250k at 0/1/3/6/12 months. |
| **Status** | ⏭ |

### TC-B-05 — Payment Plan Uses Custom Template
| | |
|---|---|
| **Pre-condition** | Create a template with 2 milestones: 30% at 0m, 70% at 6m. Assign to Property. |
| **Steps** | Submit a booking for a unit in that property (base_price = 1,000,000) |
| **Expected** | 2 Payment Plan records: 300,000 and 700,000. |
| **Status** | ⏭ |

### TC-B-06 — No Payment Plan if Base Price is Zero
| | |
|---|---|
| **Steps** | Create unit with base_price = 0. Submit booking. |
| **Expected** | No Payment Plan records created. No error. |
| **Status** | ⏭ |

### TC-B-07 — Cancel Booking Releases Unit
| | |
|---|---|
| **Steps** | Submit a booking → Cancel it |
| **Expected** | booking_status = "Cancelled". Unit availability_status = "Available". |
| **Status** | ⏭ |

---

## Module: Payment Plan

### TC-PP-01 — Generate Invoice (Happy Path)
| | |
|---|---|
| **Use Case** | UC-04 |
| **Pre-condition** | Property Unit has item_code set. Booking submitted. |
| **Steps** | Open a Payment Plan (status=Pending) → Actions → "Generate Invoice" → Confirm |
| **Expected** | Sales Invoice created in ERPNext. payment_status = "Invoiced". Invoice link visible. |
| **Status** | ⏭ |

### TC-PP-02 — Generate Invoice Fails Without item_code
| | |
|---|---|
| **Pre-condition** | Property Unit has no item_code and unit_type "Plot" does not exist as ERPNext Item. |
| **Steps** | Open Payment Plan → Generate Invoice |
| **Expected** | Error: "Item 'Plot' not found. Please create an Item named 'Plot'..." |
| **Status** | ⏭ |

### TC-PP-03 — Cannot Generate Invoice Twice
| | |
|---|---|
| **Steps** | Generate invoice on a Payment Plan → attempt Generate Invoice again |
| **Expected** | Error: "Invoice already generated for this milestone". Button not visible on UI. |
| **Status** | ⏭ |

### TC-PP-04 — Generate Invoice Button Hidden When Invoiced
| | |
|---|---|
| **Steps** | After invoice is generated, reload the Payment Plan form |
| **Expected** | "Generate Invoice" button is gone. "View Invoice" button is shown. |
| **Status** | ⏭ |

### TC-PP-05 — Amount Validation
| | |
|---|---|
| **Steps** | Manually create a Payment Plan with amount = 0 → Save |
| **Expected** | Error: "Amount must be greater than zero" |
| **Status** | ⏭ |

---

## Module: Payment Plan Template

### TC-PT-01 — Create Template (Happy Path)
| | |
|---|---|
| **Use Case** | UC-09 |
| **Steps** | New Template → add 2 milestones: 40% at 0m, 60% at 6m → Save |
| **Expected** | Template saved. |
| **Status** | ⏭ |

### TC-PT-02 — Percentages Must Total 100
| | |
|---|---|
| **Steps** | Create template with milestones totalling 90% → Save |
| **Expected** | Error: "Milestone percentages must total 100%. Current total: 90.0%" |
| **Status** | ⏭ |

---

## Module: Property Allocation (Sale)

### TC-A-01 — Submit Sale Allocation (Happy Path)
| | |
|---|---|
| **Use Case** | UC-05 |
| **Steps** | New Allocation → type=Sale, customer, property_unit (Booked), start_date → Submit |
| **Expected** | Status = Active. Unit availability_status = "Allocated". Linked agreement_status = "Active". |
| **Status** | ⏭ |

### TC-A-02 — Cancel Allocation Releases Unit
| | |
|---|---|
| **Steps** | Submit allocation → Cancel |
| **Expected** | Status = Terminated. Unit availability_status = "Available". |
| **Status** | ⏭ |

### TC-A-03 — End Date Before Start Date Blocked
| | |
|---|---|
| **Steps** | Allocation with start_date=2025-01-01, end_date=2024-12-31 → Save |
| **Expected** | Error: "End Date cannot be before Start Date" |
| **Status** | ⏭ |

---

## Module: Property Allocation (Lease/Rental — Recurring Billing)

### TC-LB-01 — Submit Lease Allocation Sets Next Billing Date
| | |
|---|---|
| **Use Case** | UC-06 |
| **Steps** | Allocation type=Lease, rent_amount=25000, billing_frequency=Monthly, billing_day=1, start_date=2025-07-15 → Submit |
| **Expected** | next_billing_date = 2025-07-01 (billing_day applied to start month). Unit status = "Leased". |
| **Status** | ⏭ |

### TC-LB-02 — Billing Engine Generates Invoice on Due Date
| | |
|---|---|
| **Pre-condition** | Active lease allocation with next_billing_date = today. Rent Item Code set in Settings. |
| **Steps** | Run `billing_engine.run_daily_billing()` |
| **Expected** | Sales Invoice created for rent_amount. Rent Invoice Log record created. next_billing_date advanced by 1 month. |
| **Status** | ⏭ |

### TC-LB-03 — Billing Engine Does Not Double-Invoice
| | |
|---|---|
| **Steps** | Run billing engine twice on the same day for the same allocation |
| **Expected** | Only one invoice created. Second run advances date, sees no allocations due. |
| **Status** | ⏭ |

### TC-LB-04 — Billing Engine Respects Frequency
| | |
|---|---|
| **Steps** | Lease allocation with billing_frequency=Quarterly. Run engine. |
| **Expected** | next_billing_date advances by 3 months. |
| **Status** | ⏭ |

### TC-LB-05 — Billing Engine Auto-Expires Past End Date
| | |
|---|---|
| **Steps** | Lease allocation with end_date = yesterday. Run engine. |
| **Expected** | Allocation status → "Expired". No invoice generated. |
| **Status** | ⏭ |

### TC-LB-06 — Rent Fields Not Shown for Sale Allocations
| | |
|---|---|
| **Steps** | Open Allocation form with allocation_type = Sale |
| **Expected** | Recurring Billing section not visible. |
| **Status** | ⏭ |

### TC-LB-07 — Billing Fails Gracefully Without Rent Item
| | |
|---|---|
| **Pre-condition** | Property Core Settings has no rent_item_code. Unit has no item_code. unit_type "Flat" not an ERPNext Item. |
| **Steps** | Run billing engine for a Flat unit |
| **Expected** | Error logged to Frappe Error Log. Other allocations continue processing. |
| **Status** | ⏭ |

### TC-LB-08 — Billing Day Clamped for Short Months
| | |
|---|---|
| **Steps** | Lease with billing_day=31, start_date in February → Submit |
| **Expected** | next_billing_date set to last day of February (28 or 29). No crash. |
| **Status** | ⏭ |

---

## Module: Property Agreement — Security Deposit

### TC-SD-01 — Record Security Deposit (Happy Path)
| | |
|---|---|
| **Use Case** | UC-07 |
| **Pre-condition** | Agreement with agreement_status=Active, security_deposit_amount=50000. Settings configured. |
| **Steps** | Click Deposit → "Record Security Deposit" → Confirm |
| **Expected** | Journal Entry created (Dr Receivable / Cr Security Deposit Account). security_deposit_received = 1. JE linked. |
| **Status** | ⏭ |

### TC-SD-02 — Cannot Record Deposit Twice
| | |
|---|---|
| **Steps** | Record deposit → attempt to record again |
| **Expected** | Error: "Security deposit journal entry already exists: JV-XXXX". Button not visible. |
| **Status** | ⏭ |

### TC-SD-03 — Record Deposit Without Amount Blocked
| | |
|---|---|
| **Steps** | Agreement with security_deposit_amount = 0 → attempt Record Deposit |
| **Expected** | Error: "Please set a Security Deposit Amount before recording the deposit" |
| **Status** | ⏭ |

### TC-SD-04 — Record Deposit Without Settings Blocked
| | |
|---|---|
| **Pre-condition** | Property Core Settings has no security_deposit_account set. |
| **Steps** | Attempt Record Security Deposit |
| **Expected** | Error: "Please configure 'Security Deposit Account' in Property Core Settings" |
| **Status** | ⏭ |

### TC-SD-05 — Refund Security Deposit on Termination
| | |
|---|---|
| **Use Case** | UC-08 |
| **Pre-condition** | Deposit recorded. agreement_status = Terminated. |
| **Steps** | Click Deposit → "Refund Security Deposit" → Confirm |
| **Expected** | Journal Entry cancelled. security_deposit_received = 0. Refund button disappears. |
| **Status** | ⏭ |

### TC-SD-06 — Deposit Pending Banner
| | |
|---|---|
| **Steps** | Open agreement with deposit_amount set but not received |
| **Expected** | Orange intro banner: "Security deposit of ₹X is pending." |
| **Status** | ⏭ |

### TC-SD-07 — Deposit Received Banner
| | |
|---|---|
| **Steps** | Open agreement after deposit is recorded |
| **Expected** | Green intro banner: "Security deposit received and recorded." |
| **Status** | ⏭ |

### TC-SD-08 — Date Validation on Agreement
| | |
|---|---|
| **Steps** | Agreement with end_date before start_date → Save |
| **Expected** | Error: "End Date cannot be before Start Date" |
| **Status** | ⏭ |

---

## Module: Customer KYC

### TC-KYC-01 — KYC Fields Appear on Customer Form
| | |
|---|---|
| **Use Case** | UC-12 |
| **Pre-condition** | property_core installed and migrated |
| **Steps** | Open any Customer record |
| **Expected** | "KYC & Verification" and "Personal & Financial Details" sections visible. kyc_status defaults to "Pending". |
| **Status** | ⏭ |

### TC-KYC-02 — Mark KYC Verified (Happy Path)
| | |
|---|---|
| **Steps** | Open Customer → fill id_type, id_number, upload id_document → click KYC → "Mark KYC Verified" → Confirm |
| **Expected** | kyc_status = "Verified". kyc_verified_on = today. kyc_verified_by = current user. Green intro banner shown. |
| **Status** | ⏭ |

### TC-KYC-03 — Verified Fields Auto-Stamped
| | |
|---|---|
| **Steps** | After marking verified, reload the Customer form |
| **Expected** | kyc_verified_on and kyc_verified_by are read-only and populated. Verify/Reject buttons gone. |
| **Status** | ⏭ |

### TC-KYC-04 — Reject KYC
| | |
|---|---|
| **Steps** | Open Customer with kyc_status = Pending → click KYC → "Reject KYC" |
| **Expected** | kyc_status = "Rejected". Red intro banner shown. |
| **Status** | ⏭ |

### TC-KYC-05 — Pending Banner Shown by Default
| | |
|---|---|
| **Steps** | Create a new Customer and save |
| **Expected** | Orange banner: "KYC verification is pending for this customer." |
| **Status** | ⏭ |

### TC-KYC-06 — All 14 KYC Fields Saveable
| | |
|---|---|
| **Steps** | Fill all KYC fields: id_type, id_number, id_document, date_of_birth, nationality, occupation, annual_income, pan_number, gst_number, address_proof_type, address_proof_document → Save |
| **Expected** | All 14 fields saved correctly. No errors. |
| **Status** | ⏭ |

### TC-KYC-07 — Verified/Rejected Fields Hidden When Pending
| | |
|---|---|
| **Steps** | Open Customer with kyc_status = Pending |
| **Expected** | kyc_verified_on and kyc_verified_by fields hidden (depends_on condition). |
| **Status** | ⏭ |

### TC-KYC-08 — KYC Fields Not Lost on ERPNext Upgrade
| | |
|---|---|
| **Steps** | Run `bench update` → re-migrate → open Customer |
| **Expected** | All KYC custom fields still present. No data lost. |
| **Status** | ⏭ |

---

## Module: Property Core Settings

### TC-CS-01 — Settings Required for Security Deposit
| | |
|---|---|
| **Steps** | Leave security_deposit_account blank in Settings. Attempt to record a deposit. |
| **Expected** | Blocked with clear error. |
| **Status** | ⏭ |

### TC-CS-02 — Settings Required for Rent Billing
| | |
|---|---|
| **Steps** | Leave rent_item_code blank. Unit has no item_code. Run billing engine. |
| **Expected** | Error logged. Invoice not generated. |
| **Status** | ⏭ |

### TC-CS-03 — Late Fee Settings Saved
| | |
|---|---|
| **Steps** | Enable Late Fees, set Grace Period = 7, Percentage = 2, Late Fee Item Code → Save |
| **Expected** | All fields saved without error. |
| **Status** | ⏭ |

---

## Module: Property Amenities

### TC-AM-01 — Add Amenity Row
| | |
|---|---|
| **Use Case** | UC-13 |
| **Steps** | Open Property → expand Amenities → Add Row → fill amenity_name="Swimming Pool", amenity_type="Recreation" → Save |
| **Expected** | Amenity row saved on Property. Visible on re-open. |
| **Status** | ⏭ |

### TC-AM-02 — Multiple Amenity Types
| | |
|---|---|
| **Steps** | Add rows: "CCTV" (Security), "Solar Panels" (Green), "Gym" (Recreation) → Save |
| **Expected** | All three rows saved. Type dropdown options: Basic / Security / Recreation / Commercial / Green / Smart Home. |
| **Status** | ⏭ |

### TC-AM-03 — Amenities Section Collapsed by Default
| | |
|---|---|
| **Steps** | Open a Property form |
| **Expected** | Amenities section is collapsed. Main fields visible without scrolling. |
| **Status** | ⏭ |

---

## Module: Project Documents

### TC-PD-01 — Attach Project Document
| | |
|---|---|
| **Use Case** | UC-14 |
| **Steps** | Open Property → expand Project Documents → Add Row → fill document_name="Title Deed", document_type="Title Deed", upload file → Save |
| **Expected** | Document row saved. File link visible on re-open. |
| **Status** | ⏭ |

### TC-PD-02 — Document Expiry Date
| | |
|---|---|
| **Steps** | Add document row with expiry_date set 1 year from today → Save |
| **Expected** | expiry_date stored and visible in the table. |
| **Status** | ⏭ |

### TC-PD-03 — Multiple Document Types
| | |
|---|---|
| **Steps** | Add rows with types: Layout Plan, NOC, Encumbrance Certificate |
| **Expected** | All type options available in dropdown. Rows saved correctly. |
| **Status** | ⏭ |

---

## Module: Lease Renewal

### TC-LR-01 — Renew Lease (Happy Path)
| | |
|---|---|
| **Use Case** | UC-15 |
| **Steps** | Submit a Lease allocation → click Actions → Renew Lease → set new_end_date = 1 year ahead, escalation_percent = 0 → Renew |
| **Expected** | end_date updated. rent_amount unchanged. Success alert shown. |
| **Status** | ⏭ |

### TC-LR-02 — Renew with Rent Escalation
| | |
|---|---|
| **Steps** | Active Lease with rent_amount = 25000 → Renew Lease with escalation_percent = 10 → Renew |
| **Expected** | rent_amount updated to 27500. new_end_date set. Alert shows new rent amount. |
| **Status** | ⏭ |

### TC-LR-03 — Renewal Blocked on Non-Lease Allocation
| | |
|---|---|
| **Steps** | Submit a Sale allocation → Actions → Renew Lease |
| **Expected** | "Renew Lease" button not visible (only shown for Lease/Rental types). |
| **Status** | ⏭ |

### TC-LR-04 — Renewal Blocked on Cancelled Allocation
| | |
|---|---|
| **Steps** | Call renew_lease() API directly on a cancelled allocation |
| **Expected** | Server throws "Only active submitted allocations can be renewed." |
| **Status** | ⏭ |

### TC-LR-05 — New End Date Required
| | |
|---|---|
| **Steps** | Open Renew Lease dialog → leave New End Date blank → click Renew |
| **Expected** | Dialog validation blocks submission. "New End Date is mandatory." |
| **Status** | ⏭ |

---

## Module: Late Fee Automation

### TC-LF-01 — Late Fee Applied After Grace Period
| | |
|---|---|
| **Use Case** | UC-16 |
| **Steps** | 1. Enable late fees in Settings (grace=5, pct=2, item configured). 2. Create a Payment Plan milestone with due_date = 6 days ago, payment_status=Pending. 3. Run billing engine. |
| **Expected** | late_fee_applied = 1. late_fee_amount = milestone_amount × 2%. Sales Invoice created and linked in late_fee_invoice. payment_status = Overdue. |
| **Status** | ⏭ |

### TC-LF-02 — Within Grace Period — No Fee
| | |
|---|---|
| **Steps** | Same config. Milestone due_date = 3 days ago (within 5-day grace). Run billing engine. |
| **Expected** | late_fee_applied = 0. No invoice created. payment_status unchanged. |
| **Status** | ⏭ |

### TC-LF-03 — Fee Not Applied Twice
| | |
|---|---|
| **Steps** | Run billing engine on a milestone that already has late_fee_applied = 1. |
| **Expected** | No second invoice created. billing engine skips due to filter on late_fee_applied = 0. |
| **Status** | ⏭ |

### TC-LF-04 — Late Fees Disabled — No Action
| | |
|---|---|
| **Steps** | Set enable_late_fees = unchecked in Settings. Create overdue milestone. Run billing engine. |
| **Expected** | No late fee applied. apply_late_fees() returns immediately. |
| **Status** | ⏭ |

### TC-LF-05 — Missing Late Fee Item Logs Error
| | |
|---|---|
| **Steps** | Enable late fees but set late_fee_item_code to a non-existent ERPNext Item. Run billing engine on overdue milestone. |
| **Expected** | Frappe Error Log entry created. Other milestones still processed. |
| **Status** | ⏭ |

### TC-LF-06 — Already Invoiced Milestone Not Charged
| | |
|---|---|
| **Steps** | Milestone with payment_status = Invoiced (not Pending). Run billing engine. |
| **Expected** | Late fee NOT applied (filter requires payment_status = Pending). |
| **Status** | ⏭ |

---

## Module: Role Permissions

### TC-RO-01 — Property Owner Read Access
| | |
|---|---|
| **Steps** | Login as user with Property Owner role only → navigate to Property list |
| **Expected** | Property list loads. No Create/Edit/Delete buttons visible. |
| **Status** | ⏭ |

### TC-RO-02 — Property Owner Cannot Book
| | |
|---|---|
| **Steps** | Property Owner user → Property Booking → New |
| **Expected** | Permission denied error. |
| **Status** | ⏭ |

### TC-RO-03 — Tenant Can Read Agreement
| | |
|---|---|
| **Steps** | Login as user with Tenant role → open Property Agreement |
| **Expected** | Agreement visible. Print button available. No edit allowed. |
| **Status** | ⏭ |

### TC-RO-04 — Tenant Can Read Payment Plan
| | |
|---|---|
| **Steps** | Tenant user → open Payment Plan list |
| **Expected** | Payment Plans visible. Print available. No write access. |
| **Status** | ⏭ |

### TC-RO-05 — Tenant Cannot Access Property Booking
| | |
|---|---|
| **Steps** | Tenant user → navigate to Property Booking |
| **Expected** | Permission denied. |
| **Status** | ⏭ |

---

## Module: Issue & Work Order

> **Revised 2026-07-23:** Maintenance Request retired entirely (TC-MR-* removed) — Issue is now the single complaint/query entry point, Work Order links directly to Issue. See USE_CASES.md UC-17/UC-18.

### TC-IWO-01 — Raise an Issue Linked to a Unit
| | |
|---|---|
| **Use Case** | UC-17 |
| **Steps** | New Issue → set Customer, Property Unit, Subject="Leaking tap", Priority → Save |
| **Expected** | Record created with status=Open. |
| **Status** | ⏭ |

### TC-IWO-02 — Create Work Order from Issue
| | |
|---|---|
| **Use Case** | UC-18 |
| **Steps** | Open the Issue → Actions → Create Work Order |
| **Expected** | New Work Order form opens with `issue` and `property_unit` pre-filled. |
| **Status** | ⏭ (button not checked in browser; underlying doc creation verified via console) |

### TC-IWO-03 — Work Order Completion Resolves the Issue
| | |
|---|---|
| **Steps** | Create a Work Order linked to an Issue → set status=Completed → Save |
| **Expected** | Linked Issue → status=Resolved, `resolution_details` filled from the Work Order description, `Issue.work_order` populated. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (`ISS-2026-00002` → Resolved after `WO-0003` completed) |

### TC-IWO-04 — Work Order Status Not Forced Onto Issue Early
| | |
|---|---|
| **Steps** | Create a Work Order linked to an Issue, set status=Assigned (not Completed) |
| **Expected** | Issue's own `status` stays unchanged (still Open); only `work_order` backlink is set. Work Order's own status tracks the granular dispatch state, not mirrored onto Issue. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 |

### TC-IWO-05 — Work Order Can Stand Alone (No Issue)
| | |
|---|---|
| **Steps** | Create a Work Order with `issue` left blank (internal/preventive work) |
| **Expected** | Saves fine; no error from the (optional) Issue sync. |
| **Status** | ⏭ |

---

## Module: Maintenance Plan Template (Recurring Billing)

### TC-MPT-01 — Create Template With Month-wise Rows
| | |
|---|---|
| **Use Case** | UC-32 |
| **Steps** | New Maintenance Plan Template → add rows month_no=1 amount=2000, month_no=2 amount=2000 → set Repeat Every N Months=1, Repeat Amount=2000 → Save |
| **Expected** | Saves without error. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 |

### TC-MPT-02 — Row Needs Month No. or Fixed Due Date
| | |
|---|---|
| **Steps** | Add a schedule row with both `month_no` and `fixed_due_date` blank → Save |
| **Expected** | Throws: "Row N: set either Month No. or Fixed Due Date" |
| **Status** | ⏭ |

### TC-MPT-03 — Assign Template to a Unit and Auto-Bill
| | |
|---|---|
| **Use Case** | UC-33 |
| **Steps** | Set Property Core Settings → Maintenance Item Code. Set a Property Unit's Maintenance Plan Template + Maintenance Start Date (2 months ago) → run `maintenance_billing.run_daily_maintenance_billing()` |
| **Expected** | One submitted Sales Invoice per elapsed period (month 1, month 2 from the template, month 3 from the repeat rule) — 3 invoices total for a 2-months-back start date. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (3 invoices: 2026-05, 2026-06, 2026-07, ₹2000 each, all submitted) |

### TC-MPT-04 — No Duplicate Invoice on Re-run
| | |
|---|---|
| **Steps** | Run the scheduler again immediately after TC-MPT-03 |
| **Expected** | No additional invoices created — same 3 as before. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 |

### TC-MPT-05 — Paused Unit Not Billed
| | |
|---|---|
| **Steps** | Set `Pause Maintenance Billing` on a unit with a template assigned → run the scheduler |
| **Expected** | No invoice generated for that unit while paused. |
| **Status** | ⏭ |

---

## Module: Inspection Checklist

### TC-INS-01 — Create Inspection (Happy Path)
| | |
|---|---|
| **Use Case** | UC-19 |
| **Steps** | New Inspection Checklist → property_unit, type=Move-In, date=today → Save |
| **Expected** | Record created with status=Draft. |
| **Status** | ⏭ |

### TC-INS-02 — Load Default Items
| | |
|---|---|
| **Steps** | On a new inspection with empty checklist_items → Actions → Load Default Items |
| **Expected** | 12 items pre-populated with category filled. condition field blank (to be filled by inspector). |
| **Status** | ⏭ |

### TC-INS-03 — Cannot Complete Without Items
| | |
|---|---|
| **Steps** | Set status=Completed on a checklist with empty checklist_items → Save |
| **Expected** | Validation error: "Add at least one checklist item before marking as Completed" |
| **Status** | ⏭ |

### TC-INS-04 — All Condition Options Available
| | |
|---|---|
| **Steps** | Add a checklist item → click condition dropdown |
| **Expected** | Options: OK / Minor Issue / Major Issue / N/A |
| **Status** | ⏭ |

---

## Module: Utility Meter & Utility Bill

### TC-UM-01 — Create Utility Meter
| | |
|---|---|
| **Use Case** | UC-20 |
| **Steps** | New Utility Meter → property_unit, utility_type=Electricity, meter_number="E001", rate_per_unit=8, customer, utility_item_code → Save |
| **Expected** | Meter saved. Utility Bills connection shown. |
| **Status** | ⏭ |

### TC-UM-02 — Zero Rate Blocked
| | |
|---|---|
| **Steps** | Create Utility Meter with rate_per_unit=0 → Save |
| **Expected** | Validation error: "Rate per Unit must be greater than zero" |
| **Status** | ⏭ |

### TC-UB-01 — Create Utility Bill (Happy Path)
| | |
|---|---|
| **Steps** | New Utility Bill → utility_meter, period_start, period_end, previous_reading=100, current_reading=250 → Save |
| **Expected** | units_consumed=150. amount=150×rate. property_unit and customer auto-filled from meter. |
| **Status** | ⏭ |

### TC-UB-02 — Live Calculation in UI
| | |
|---|---|
| **Steps** | On Utility Bill form → enter previous_reading=200, current_reading=350 |
| **Expected** | units_consumed and amount update live in the UI without saving. |
| **Status** | ⏭ |

### TC-UB-03 — Current Reading Below Previous Blocked
| | |
|---|---|
| **Steps** | Set current_reading < previous_reading → Save |
| **Expected** | Validation error: "Current Reading cannot be less than Previous Reading" |
| **Status** | ⏭ |

### TC-UB-04 — Generate Invoice
| | |
|---|---|
| **Steps** | Saved Utility Bill with status=Draft → Actions → Generate Invoice → Confirm |
| **Expected** | Sales Invoice created. invoice field linked. status → Invoiced. "View Invoice" button appears. |
| **Status** | ⏭ |

### TC-UB-05 — Generate Invoice Blocked Without Item Code
| | |
|---|---|
| **Steps** | Utility Meter has no utility_item_code → Generate Invoice on linked bill |
| **Expected** | Error: "Set 'Utility Item Code' on the Utility Meter..." |
| **Status** | ⏭ |

### TC-UB-06 — No Double Invoice
| | |
|---|---|
| **Steps** | Already-invoiced Utility Bill → Actions → Generate Invoice |
| **Expected** | Error: "Invoice already generated: SI-XXXX" |
| **Status** | ⏭ |

---

## Module: Commission Rule

### TC-CR-01 — Create Percentage Commission Rule
| | |
|---|---|
| **Use Case** | UC-21 |
| **Steps** | New Commission Rule → rule_name="Standard 2%", commission_type=Percentage, commission_rate=2, is_active=1 → Save |
| **Expected** | Rule saved. Applies to all properties and sales persons. |
| **Status** | ⏭ |

### TC-CR-02 — Rate Over 100% Blocked
| | |
|---|---|
| **Steps** | Commission Rule with commission_type=Percentage, commission_rate=150 → Save |
| **Expected** | Validation error: "Commission Rate cannot exceed 100% for Percentage type" |
| **Status** | ⏭ |

### TC-CR-03 — Flat Commission Rule
| | |
|---|---|
| **Steps** | commission_type=Flat, commission_rate=50000 (fixed ₹50k per booking) → Save |
| **Expected** | Rule saved. No percentage cap validation triggered. |
| **Status** | ⏭ |

### TC-CR-04 — Zero Rate Blocked
| | |
|---|---|
| **Steps** | commission_rate=0 → Save |
| **Expected** | Validation error: "Commission Rate must be greater than zero" |
| **Status** | ⏭ |

---

## Module: Commission Entry

### TC-CE-01 — Auto-Created on Booking Submit
| | |
|---|---|
| **Use Case** | UC-22 |
| **Steps** | 1. Create active Commission Rule (2%, global). 2. Create and submit a Booking with sales_person set and booking_amount=1000000. |
| **Expected** | Commission Entry created: commission_amount=20000 (2%), status=Pending, booking linked. |
| **Status** | ⏭ |

### TC-CE-02 — No Entry Without Sales Person
| | |
|---|---|
| **Steps** | Submit a Booking with no sales_person |
| **Expected** | No Commission Entry created. No error thrown. |
| **Status** | ⏭ |

### TC-CE-03 — No Entry Without Matching Rule
| | |
|---|---|
| **Steps** | No Commission Rule exists (or all inactive). Submit Booking with sales_person. |
| **Expected** | No Commission Entry created. No error thrown. |
| **Status** | ⏭ |

### TC-CE-04 — Specific Rule Wins Over Global
| | |
|---|---|
| **Steps** | Global rule: 2%. Property-specific rule for this property: 3%. Submit Booking. |
| **Expected** | Commission Entry uses 3% (property-specific wins). |
| **Status** | ⏭ |

### TC-CE-05 — Entry Cancelled on Booking Cancel
| | |
|---|---|
| **Steps** | Submit Booking → verify Commission Entry Pending → Cancel Booking |
| **Expected** | Commission Entry status → Cancelled. |
| **Status** | ⏭ |

---

## Module: Commission Settlement

### TC-CS2-01 — Load Pending Entries
| | |
|---|---|
| **Use Case** | UC-23 |
| **Steps** | New Commission Settlement → select sales_person → Actions → Load Pending Entries |
| **Expected** | Child table populated with all Pending commission entries for that sales person. total_amount auto-summed. |
| **Status** | ⏭ |

### TC-CS2-02 — Submit Settlement Marks Entries Settled
| | |
|---|---|
| **Steps** | Commission Settlement with 3 Pending entries → Submit |
| **Expected** | All 3 Commission Entries → status=Settled, settlement field linked. Settlement status=Submitted. |
| **Status** | ⏭ |

### TC-CS2-03 — Cannot Settle Already-Settled Entry
| | |
|---|---|
| **Steps** | Try to create a second settlement with the same already-Settled Commission Entry |
| **Expected** | Validation error: "Commission Entry is not in Pending status" |
| **Status** | ⏭ |

### TC-CS2-04 — Cancel Settlement Reverts Entries
| | |
|---|---|
| **Steps** | Cancel a Submitted settlement |
| **Expected** | All linked Commission Entries → status=Pending. Settlement status=Draft. |
| **Status** | ⏭ |

### TC-CS2-05 — Wrong Sales Person Entry Blocked
| | |
|---|---|
| **Steps** | Settlement for Sales Person A — manually add a Commission Entry belonging to Sales Person B |
| **Expected** | Validation error: "Commission Entry belongs to a different Sales Person" |
| **Status** | ⏭ |

### TC-CS2-06 — Total Amount Computed
| | |
|---|---|
| **Steps** | Add 3 entries with amounts 10000, 20000, 15000 → before_validate |
| **Expected** | total_amount = 45000 |
| **Status** | ⏭ |

---

## Module: CRM ↔ Property Link

### TC-CRM-01 — Opportunity Saves With Property/Unit
| | |
|---|---|
| **Use Case** | UC-26 |
| **Steps** | New Opportunity → expand Property Interest section → set property and property_unit → Save |
| **Expected** | Fields save correctly; values persist on reload. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (`CRM-OPP-2026-00001` saved with property="Emerald Heights", property_unit="UNIT-0004") |

### TC-CRM-02 — Property Shows Opportunities Connection
| | |
|---|---|
| **Steps** | Create an Opportunity linked to a Property → open the Property form |
| **Expected** | "Opportunities" connection appears under the Property's Connections, alongside "Units". |
| **Status** | ⏭ (fields verified; connection-panel rendering not checked in browser) |

---

## Module: Customer Portal API

### TC-CP-01 — Portal User Auto-Provisioned on Booking
| | |
|---|---|
| **Use Case** | UC-28 |
| **Steps** | Create a Customer with a primary Contact (with email) → no existing Portal User → create+insert a Property Booking for that customer |
| **Expected** | A Website User is created from the contact email (role Customer), and a Portal User row links it to the Customer — all without blocking the booking insert. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (`BKG-0005` created; `portal.test@example.com` User + Portal User row both created) |

### TC-CP-02 — Portal User Not Duplicated
| | |
|---|---|
| **Steps** | Submit a second Property Booking for a customer who already has a Portal User |
| **Expected** | No duplicate User/Portal User created; `ensure_portal_user()` returns early. |
| **Status** | ⏭ |

### TC-CP-03 — customer_portal_get Returns Own Data Only
| | |
|---|---|
| **Use Case** | UC-28 |
| **Steps** | Log in as a portal customer → call `customer_portal_get()` |
| **Expected** | Returns only that customer's bookings (with Payment Plan rows labelled Paid/Overdue/Due Soon/Upcoming), units, agreements, and issues. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (booking `BKG-0005` returned with 4 Payment Plan rows correctly labelled Due Soon/Upcoming; unit UNIT-0004 shown) |

### TC-CP-04 — raise_issue Creates Issue With Property Link
| | |
|---|---|
| **Use Case** | UC-27 |
| **Steps** | Log in as a portal customer who owns `UNIT-0004` → call `raise_issue("Water leakage in bathroom", "...", "UNIT-0004")` |
| **Expected** | An Issue is created with `customer` and `property_unit` set, status Open. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (`ISS-2026-00001` created) |

### TC-CP-05 — raise_issue Blocks Unowned Unit
| | |
|---|---|
| **Use Case** | UC-27 |
| **Steps** | Log in as a portal customer → call `raise_issue(...)` with a `property_unit` that belongs to a *different* customer |
| **Expected** | Throws: "Selected unit does not belong to your account". No Issue created. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (tried `UNIT-0001`, owned by a different customer — correctly rejected) |

### TC-CP-06 — Portal APIs Require Login
| | |
|---|---|
| **Steps** | Call `customer_portal_get()` or `raise_issue()` as Guest |
| **Expected** | Throws: "Please login". |
| **Status** | ⏭ |

---

## Module: Payment Plan Auto-Invoicing

### TC-PPB-01 — Due Milestone Auto-Invoiced
| | |
|---|---|
| **Use Case** | UC-29 |
| **Steps** | Submit a Property Booking (Payment Plan auto-generates) → manually run `payment_plan_billing.run_daily_payment_plan_billing()` on the day a milestone is due |
| **Expected** | That milestone's Sales Invoice is auto-created; `payment_status` → Invoiced. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (PP-0009 "Token", due today, auto-invoiced as `ACC-SINV-2026-00007`) |

### TC-PPB-02 — Future Milestones Untouched
| | |
|---|---|
| **Use Case** | UC-29 |
| **Steps** | Same run as TC-PPB-01 → check the other (not-yet-due) Payment Plan rows on the same booking |
| **Expected** | Rows with a future due_date remain `payment_status = Pending`, no invoice. |
| **Status** | ✅ Pass — verified via bench console on review.site, 2026-07-23 (PP-0010/0011/0012 left Pending, invoice=NULL) |

### TC-PPB-03 — Already-Invoiced Milestone Skipped
| | |
|---|---|
| **Steps** | Run the scheduler twice in a row on the same due milestone |
| **Expected** | Second run does not create a duplicate invoice (filtered out by `invoice in ["", None]`). |
| **Status** | ⏭ |

---

## Regression Checklist

Run after every code change:

- [ ] TC-KYC-01: KYC fields visible on Customer form
- [ ] TC-KYC-02: Mark KYC Verified stamps date + user
- [ ] TC-B-01: Submit booking → unit becomes Booked
- [ ] TC-B-02: Double booking blocked
- [ ] TC-B-07: Cancel booking → unit becomes Available
- [ ] TC-PP-01: Invoice generated correctly
- [ ] TC-A-01: Sale allocation → unit becomes Allocated
- [ ] TC-LB-02: Billing engine generates rent invoice
- [ ] TC-AM-01: Amenity row saved on Property
- [ ] TC-PD-01: Project document attached to Property
- [ ] TC-LR-01: Lease renewed with new end date
- [ ] TC-LR-02: Rent escalation applied correctly
- [ ] TC-LF-01: Late fee applied after grace period
- [ ] TC-LF-03: Late fee not applied twice
- [ ] TC-RO-01: Property Owner has read-only access
- [ ] TC-RO-03: Tenant can read Agreement
- [ ] TC-IWO-01: Issue created with status=Open
- [ ] TC-IWO-03: Work Order completion resolves the linked Issue
- [ ] TC-MPT-03: Maintenance Plan Template auto-bills elapsed periods
- [ ] TC-MPT-04: Re-running maintenance billing creates no duplicates
- [ ] TC-INS-02: Load Default Items populates 12 checklist rows
- [ ] TC-UB-01: Utility Bill calculates units and amount correctly
- [ ] TC-UB-04: Generate Invoice creates Sales Invoice
- [ ] TC-CE-01: Commission Entry auto-created on booking submit
- [ ] TC-CE-04: Property-specific rule wins over global
- [ ] TC-CS2-02: Submit settlement marks entries as Settled
- [ ] TC-SD-01: Security deposit JE created correctly
- [ ] TC-CRM-01: Opportunity saves with property/property_unit
- [ ] TC-CP-01: Portal user auto-provisioned on booking
- [ ] TC-CP-04: raise_issue creates Issue with property link
- [ ] TC-CP-05: raise_issue blocks a unit that isn't the caller's
- [ ] TC-PPB-01: Due Payment Plan milestone auto-invoiced

---

## Test Data Setup Script

Run once on a fresh dev site:

```python
# bench --site dev.site.com console

import frappe

# 1. Company (use existing or create)
company = frappe.defaults.get_global_default("company")

# 2. ERPNext Items
for item_name in ["Flat", "Plot", "Monthly Rent"]:
    if not frappe.db.exists("Item", item_name):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": item_name,
            "item_name": item_name,
            "item_group": "Services",
            "is_stock_item": 0,
        }).insert(ignore_permissions=True)

# 3. Property Core Settings
settings = frappe.get_single("Property Core Settings")
settings.default_company = company
settings.rent_item_code = "Monthly Rent"
# settings.security_deposit_account = "Security Deposits Held - XYZ"  # set manually
settings.save(ignore_permissions=True)

# 4. Customer
if not frappe.db.exists("Customer", "Test Tenant"):
    frappe.get_doc({
        "doctype": "Customer",
        "customer_name": "Test Tenant",
        "customer_type": "Individual",
        "customer_group": "Individual",
        "territory": "All Territories",
    }).insert(ignore_permissions=True)

frappe.db.commit()
print("Test data setup complete.")
```
