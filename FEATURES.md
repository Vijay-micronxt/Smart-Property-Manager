# Smart Property Manager — Feature List

> **Last updated:** 2026-07-21 — added Customer KYC custom fields
> Update this file whenever a DocType, engine, or workflow is added, changed, or removed.

---

## Architecture

Three Frappe/ERPNext apps installed on the same bench:

```
ERPNext Core + Frappe CRM
        |
  property_core          ← lifecycle engine (this document)
  property_operations    ← maintenance & ops (skeleton)
  property_commissions   ← commissions & settlements (skeleton)
```

---

## App 1: property_core

### 1.1 DocTypes

#### Property
Master record for a real estate project.

| Field | Type | Notes |
|---|---|---|
| property_name | Data | Primary key (autoname by field) |
| property_type | Select | Township / Community / Apartment / Farmland / Commercial Complex / Industrial |
| company | Link → Company | Required |
| status | Select | Active / Inactive / Under Development / Completed |
| launch_date | Date | |
| total_area | Float | sq ft |
| address | Small Text | |
| payment_plan_template | Link → Payment Plan Template | Default milestone split for bookings under this property |
| geo_location | Geolocation | Leaflet map widget (collapsible section) |

**Connections (shown on form):** Property Units

---

#### Property Unit
Sellable / rentable unit within a Property.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | UNIT-.#### |
| property | Link → Property | Required |
| unit_number | Data | Required; unique per property (validated) |
| unit_type | Select | Plot / Flat / Villa / Office / Warehouse / Shop |
| availability_status | Select | Available / Reserved / Booked / Allocated / Leased / Maintenance Blocked — **read-only, managed by engines** |
| area | Float | sq ft |
| facing | Select | North / South / East / West / NE / NW / SE / SW |
| floor | Int | |
| base_price | Currency | Used to calculate payment plan amounts |
| item_code | Link → Item | ERPNext Item for Sales Invoice generation |
| customer | Link → Customer | Read-only; set by allocation engine |
| geo_location | Geolocation | Leaflet map (collapsible section) |

**Connections:** Property Bookings, Property Allocations

**UI Buttons:** New Booking, availability status indicator, item_code warning

---

#### Property Booking
Temporary reservation before formal allocation.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | BKG-.#### |
| customer | Link → Customer | Required |
| property_unit | Link → Property Unit | Required |
| booking_date | Date | Defaults to today |
| booking_status | Select | Draft / Reserved / Confirmed / Cancelled |
| sales_person | Link → Sales Person | |
| opportunity | Link → Opportunity | CRM link |
| booking_amount | Currency | Required |
| notes | Text | |

**Workflow:** Draft → (submit) → Confirmed → (cancel) → Cancelled

**Automation on submit:**
- Validates unit is Available (blocks double-booking)
- Sets unit status to Booked
- Auto-generates Payment Plan milestones from template or defaults

**Automation on cancel:**
- Sets unit status back to Available
- Sets booking_status to Cancelled

---

#### Property Allocation
Finalised assignment of a unit to a customer (sale, lease, rental, or assignment).

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | ALLOC-.#### |
| customer | Link → Customer | Required |
| property_unit | Link → Property Unit | Required |
| allocation_type | Select | Sale / Lease / Rental / Assignment |
| status | Select | Draft / Active / Terminated / Expired |
| start_date | Date | Required |
| end_date | Date | Optional (lease/rental expiry) |
| booking | Link → Property Booking | Source booking |
| agreement | Link → Property Agreement | Linked agreement |
| rent_amount | Currency | Lease/Rental only — rent per billing cycle |
| billing_frequency | Select | Monthly / Quarterly / Half-Yearly / Yearly |
| billing_day | Int | Day of month to generate invoice (1–28) |
| next_billing_date | Date | Read-only — managed by billing engine |

**Automation on submit:**
- Sets status to Active
- Sets unit status to Allocated (Sale) or Leased (Lease/Rental)
- Sets linked agreement status to Active
- For Lease/Rental: computes `next_billing_date` from start_date + billing_day

**Automation on cancel:**
- Sets status to Terminated
- Releases unit back to Available

**UI:** Shows next billing date in dashboard; links to Rent Invoice Log

---

#### Property Agreement
Legal document (sale deed, lease agreement, allotment letter, rental agreement).

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | AGMT-.#### |
| agreement_type | Select | Sale Agreement / Lease Agreement / Allotment Letter / Rental Agreement |
| customer | Link → Customer | Required |
| property_unit | Link → Property Unit | Required |
| agreement_status | Select | Draft / Active / Expired / Terminated |
| start_date | Date | Required |
| end_date | Date | |
| signed_date | Date | Used as JE posting date for deposit |
| document_attachment | Attach | Signed agreement PDF |
| security_deposit_amount | Currency | Refundable deposit |
| security_deposit_received | Check | Read-only; set when JE is created |
| security_deposit_journal | Link → Journal Entry | Read-only; auto-created |

**UI Buttons:**
- Record Security Deposit → creates Dr/Cr Journal Entry
- View Deposit Entry → navigates to the JE
- Refund Security Deposit → cancels JE (on terminated agreements)

**Intro banner:** Green (deposit received) / Orange (deposit pending)

---

#### Payment Plan
Installment milestone for a booking.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | PP-.#### |
| booking | Link → Property Booking | Required |
| milestone | Data | e.g. "On Foundation" |
| due_date | Date | Required |
| amount | Currency | Required (> 0 validated) |
| invoice | Link → Sales Invoice | Read-only; set on invoice generation |
| payment_status | Select | Pending / Invoiced / Paid / Overdue |

**UI Buttons:**
- Generate Invoice → calls `generate_invoice()` (visible when Pending, no invoice)
- View Invoice → navigates to Sales Invoice (visible when invoice exists)

---

#### Payment Plan Template
Configurable milestone split applied to bookings under a Property.

| Field | Type | Notes |
|---|---|---|
| template_name | Data | Primary key |
| milestones | Table → Payment Plan Milestone | List of milestone rows |

**Validation:** Milestone percentages must total exactly 100%.

**Child table — Payment Plan Milestone:**

| Field | Type | Notes |
|---|---|---|
| milestone | Data | Milestone name |
| percentage | Float | % of base_price |
| offset_months | Int | Months after booking date |

---

#### Rent Invoice Log
Tracks each auto-generated rent invoice per billing cycle.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | RINV-.#### |
| allocation | Link → Property Allocation | Required |
| period_label | Data | e.g. "Jul 2025" |
| period_start | Date | |
| period_end | Date | |
| invoice | Link → Sales Invoice | Auto-linked |
| status | Select | Invoiced / Paid / Failed |
| error_log | Small Text | Populated on billing failure |

---

#### Property Core Settings *(Single)*
One-time configuration for accounting defaults.

| Field | Notes |
|---|---|
| default_company | Required for Journal Entry creation |
| security_deposit_account | Liability account for deposit JEs |
| rent_item_code | ERPNext Item used for auto-generated rent invoices |

---

### 1.2 Business Engines

#### Availability Engine (`utils/availability_engine.py`)
Manages unit status transitions. All booking/allocation flows go through this.

| Function | Action |
|---|---|
| `assert_unit_available(unit)` | Throws if unit status is in blocked set |
| `reserve_unit(unit, customer)` | Sets status → Booked |
| `allocate_unit(unit, customer, type)` | Sets status → Allocated or Leased |
| `release_unit(unit)` | Sets status → Available, clears customer |
| `block_unit_for_maintenance(unit)` | Sets status → Maintenance Blocked |

Blocked statuses: Reserved, Booked, Allocated, Leased, Maintenance Blocked.

---

#### Allocation Engine (`utils/allocation_engine.py`)
Generates Payment Plan records on booking confirmation.

- Reads `payment_plan_template` from the linked Property
- Falls back to default 10/20/20/25/25% split over 0/1/3/6/12 months
- Skips if no `base_price` on unit or if plan already exists

---

#### Billing Engine (`utils/billing_engine.py`)
Daily scheduled job for recurring lease/rental invoicing.

- Runs via `scheduler_events → daily` in `hooks.py`
- Queries active Lease/Rental allocations where `next_billing_date <= today`
- Creates Sales Invoice per cycle using `rent_item_code` from Settings
- Logs each cycle in `Rent Invoice Log`
- Advances `next_billing_date` by billing frequency
- Auto-expires allocations past their `end_date`

---

### 1.3 Roles & Permissions

| Role | Access |
|---|---|
| Property Manager | Full CRUD + submit/cancel on all DocTypes |
| Sales User | Create/submit Bookings; read Allocations, Units |
| Finance User | Read Allocations, Payment Plans, Rent Invoice Log |
| Operations User | Read Properties, Units |
| Commission Manager | (reserved for property_commissions app) |

---

## App 2: property_operations *(Skeleton)*

Planned DocTypes: Maintenance Request, Work Order, Inspection Checklist, Utility Meter.
Not yet implemented.

---

## App 3: property_commissions *(Skeleton)*

Planned DocTypes: Commission Rule, Commission Entry, Commission Settlement.
Not yet implemented.

---

---

## Customer KYC Custom Fields

Defined in `property_core/customer_kyc.py`, applied via `custom_fields` in `hooks.py`.
Added to the Customer form after the `website` field. No ERPNext core modification.

### Section: KYC & Verification

| # | Fieldname | Type | Notes |
|---|---|---|---|
| 1 | `kyc_status` | Select | Pending / Verified / Rejected — default Pending |
| 2 | `kyc_verified_on` | Date | Visible only when status = Verified |
| 3 | `kyc_verified_by` | Link → User | Read-only; auto-set by UI button |
| 4 | `id_type` | Select | Aadhaar / PAN Card / Passport / Driving Licence / Voter ID |
| 5 | `id_number` | Data | ID document number |
| 6 | `id_document` | Attach | Scan of ID proof |

### Section: Personal & Financial Details

| # | Fieldname | Type | Notes |
|---|---|---|---|
| 7 | `date_of_birth` | Date | |
| 8 | `nationality` | Link → Country | |
| 9 | `occupation` | Data | |
| 10 | `annual_income` | Currency | For financial screening |
| 11 | `pan_number` | Data | Tax ID (India) |
| 12 | `gst_number` | Data | For commercial buyers |
| 13 | `address_proof_type` | Select | Utility Bill / Rent Agreement / Bank Statement / Passport / Aadhaar |
| 14 | `address_proof_document` | Attach | Scan of address proof |

### UI Buttons on Customer Form (customer_kyc.js)

| Button | Visible When | Action |
|---|---|---|
| Mark KYC Verified | KYC Status = Pending | Sets status=Verified, stamps date + user |
| Reject KYC | KYC Status = Pending | Sets status=Rejected |
| Colour-coded intro banner | Always | Green (Verified) / Orange (Pending) / Red (Rejected) |

---

## ERPNext Integration Points

| ERPNext DocType | Used for |
|---|---|
| Sales Invoice | Booking milestones, rent invoices |
| Journal Entry | Security deposit Dr/Cr entry |
| Payment Entry | Deposit reconciliation (user-created) |
| Customer | Linked to bookings and allocations |
| Opportunity | CRM → Booking link |
| Sales Person | Booking attribution |
| Item | Required for invoice line items |
| Account | Security deposit liability account |
| Company | All accounting entries |
