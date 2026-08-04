# Smart Property Manager — Feature List

> **Last updated:** 2026-08-04 — Customer Portal API v2 (`property_core.api.portal.*`, 28 endpoints), extensible field registry, Property ↔ ERPNext Project link
> **2026-07-23:** — Architecture unification: Maintenance Request retired, Work Order now links directly to Issue, new Maintenance Plan Template recurring billing added
> **2026-07-21:** Phase 2 & 3: property_operations (Maintenance, Work Order, Inspection, Utility) and property_commissions (Rule, Entry, Settlement) fully implemented
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

**Child tables:**
- `amenities` → Property Amenity (amenity_name, amenity_type, description) — collapsible section
- `property_documents` → Property Document (document_name, document_type, document_file, expiry_date, notes) — collapsible section

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
| late_fee_applied | Check | Read-only; set by billing engine |
| late_fee_amount | Currency | Read-only; calculated by billing engine |
| late_fee_invoice | Link → Sales Invoice | Read-only; auto-created late fee invoice |

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
One-time configuration for accounting defaults and automation.

| Field | Notes |
|---|---|
| default_company | Required for Journal Entry creation |
| security_deposit_account | Liability account for deposit JEs |
| rent_item_code | ERPNext Item used for auto-generated rent invoices |
| enable_late_fees | Toggle late fee automation (default off) |
| late_fee_grace_days | Days after due date before fee applies (default 5) |
| late_fee_percentage | Late fee as % of milestone amount |
| late_fee_item_code | ERPNext Item used for late fee Sales Invoices |

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
Daily scheduled job for recurring lease/rental invoicing and late fee enforcement.

- Runs via `scheduler_events → daily` in `hooks.py`
- Queries active Lease/Rental allocations where `next_billing_date <= today`
- Creates Sales Invoice per cycle using `rent_item_code` from Settings
- Logs each cycle in `Rent Invoice Log`
- Advances `next_billing_date` by billing frequency
- Auto-expires allocations past their `end_date`
- Calls `apply_late_fees()` at end of each daily run

**`apply_late_fees()`:**
- Reads `enable_late_fees`, `late_fee_grace_days`, `late_fee_percentage`, `late_fee_item_code` from Settings
- Finds Pending Payment Plans where `due_date < today - grace_days` and `late_fee_applied = 0`
- Creates a Sales Invoice for `amount × late_fee_percentage / 100`
- Sets `late_fee_applied = 1`, `late_fee_amount`, `late_fee_invoice`, `payment_status = Overdue`
- Errors logged per plan without stopping others

---

### 1.3 Roles & Permissions

| Role | Access |
|---|---|
| Property Manager | Full CRUD + submit/cancel on all DocTypes |
| Sales User | Create/submit Bookings; read Allocations, Units |
| Finance User | Read Allocations, Payment Plans, Rent Invoice Log |
| Operations User | Read Properties, Units |
| Commission Manager | (reserved for property_commissions app) |
| Property Owner | Read Properties, Units, Allocations, Agreements |
| Tenant | Read Agreements (own), Payment Plans (own) with print access |

#### Lease Renewal (Property Allocation)

**UI Button:** "Renew Lease" (Actions group) — visible on active Lease/Rental allocations.

**Server method:** `renew_lease(allocation_name, new_end_date, escalation_percent)`
- Sets `end_date` to `new_end_date`
- If `escalation_percent > 0`: updates `rent_amount` = current × (1 + pct/100)
- Returns `{new_end_date, new_rent_amount, escalation_applied}`
- Throws if allocation is not active/submitted or is not Lease/Rental type

---

## App 2: property_operations

### 2.1 DocTypes

#### Issue (ERPNext native — the single complaint/query entry point)
**Revised 2026-07-23:** there is no "Maintenance Request" doctype anymore. `Issue` (ERPNext's own ticketing doctype) is the one place any query or complaint gets raised, whether or not it turns out to need physical work — matches how JD's own live site works (it never had a separate Maintenance Request either). property_core adds `property_unit`; property_operations adds `work_order` on top when this optional app is installed.

| Field | Type | Notes |
|---|---|---|
| *(native)* subject, customer, raised_by, status, priority, issue_type, description, resolution_details, opening_date, via_customer_portal, SLA fields | — | Shipped by ERPNext — richer than a hand-rolled ticket doctype for free |
| property_unit | Link → Property Unit | Custom field, owned by property_core |
| work_order | Link → Work Order | Custom field, owned by property_operations; read-only, set once a Work Order is created |

**UI (when property_operations installed):** "Create Work Order" button (Actions) when a Work Order doesn't exist yet; "View Work Order" once it does.
**Portal API:** `property_core.property_core.api.customer_portal.raise_issue(subject, description, property_unit)` — see App 1.

---

#### Work Order
Operational task dispatched to resolve an Issue (or standalone internal/preventive work).

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | WO-.#### |
| issue | Link → Issue | Optional — blank for internal/preventive work with no customer complaint behind it |
| property_unit | Link → Property Unit | Required |
| status | Select | Draft / Assigned / In Progress / Completed / Cancelled |
| description | Text | Required |
| assigned_to | Link → User | |
| vendor | Link → Supplier | |
| scheduled_date | Date | |
| completed_date | Date | Auto-filled on Completed |
| estimated_cost | Currency | |
| actual_cost | Currency | |

**Automation on update:** when linked to an Issue, sets `Issue.work_order` always, and flips `Issue.status` → Resolved (with `resolution_details` from the Work Order's description) only once this Work Order is Completed — Work Order's own status already tracks the granular Assigned/In Progress dispatch state, not mirrored onto Issue.

---

#### Maintenance Plan Template *(new)*
Reusable recurring monthly maintenance/society charge plan — unrelated to Issue/Work Order, this is proactive scheduled billing, not complaint-driven. Ported from JD's own live, proven pattern.

| Field | Type | Notes |
|---|---|---|
| template_name | Data | Unique, required |
| disabled | Check | |
| schedule | Table → Maintenance Schedule Row | Month-wise charge rows |
| repeat_every_n_months | Int | 0 = stop billing after the listed months run out |
| repeat_amount | Currency | Amount charged on the repeat cadence |
| repeat_item_code | Link → Item | Optional — overrides Property Core Settings' default Item for repeat-cycle charges. Invoice-line text for repeat charges always uses the default "Maintenance charge - unit - period" text (kept simple deliberately). |

**Child table — Maintenance Schedule Row:**
| Field | Type | Notes |
|---|---|---|
| month_no | Int | Months after the unit's plan start date |
| description | Data | Optional invoice-line text (e.g. "Society Fee", "Water Charge"); defaults to "Maintenance charge - unit - period" |
| amount | Currency | Required |
| fixed_due_date | Date | Optional — bill on this exact date instead of a relative month |
| item_code | Link → Item | Optional — overrides Property Core Settings' default Item for this row (e.g. a separate Item for a different charge type) |

**Property Unit gets (custom fields, owned by property_operations):** `maintenance_plan_template` (Link), `maintenance_start_date` (Date), `pause_maintenance` (Check), `maintenance_billing_history` (HTML, read-only).
**Property Core Settings gets (custom field, owned by property_operations):** `maintenance_item_code` (Link → Item, mandatory) — the default Item used unless a row/repeat-cycle overrides it.
**Sales Invoice gets (custom fields, owned by property_operations):** `property_unit`, `maintenance_period` (used to prevent double-billing the same period).

**Automation:** daily scheduler (`maintenance_billing.run_daily_maintenance_billing`) creates + submits one Sales Invoice per newly-due period per enrolled unit. No reminder/notification logic — same standing decision as the Payment Plan billing in App 1.

**UI — Maintenance Billing History (`public/js/property_unit_maintenance.js`):** when a unit has a Maintenance Plan Template assigned, its form shows a live table (Period / Due Date / Amount / Paid / Outstanding / Status, plus a Total Billed / Total Outstanding summary) built from the unit's own maintenance Sales Invoices via `frappe.client.get_list` — not stored data, always reflects the real invoices. Registered as a second `doctype_js` entry for Property Unit alongside property_core's own `property_unit.js`; Frappe merges both when multiple apps target the same doctype, so this stays fully additive and uninstall-safe (the HTML field is covered by the same `delete_property_unit_link_fields` cleanup as the other Maintenance fields).

---

#### Inspection Checklist
Records the condition of a unit at move-in, move-out, or periodic inspection.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | INS-.#### |
| property_unit | Link → Property Unit | Required |
| inspection_type | Select | Move-In / Move-Out / Periodic / Pre-Sale |
| inspection_date | Date | Required, defaults to today |
| status | Select | Draft / In Progress / Completed |
| inspector | Link → User | |
| overall_condition | Select | Excellent / Good / Fair / Poor |
| checklist_items | Table → Inspection Checklist Item | |

**Child table — Inspection Checklist Item:**
| Field | Type | Notes |
|---|---|---|
| item_name | Data | Required |
| category | Select | Electrical / Plumbing / Structural / Fixtures / Cleanliness / Safety / Other |
| condition | Select | OK / Minor Issue / Major Issue / N/A |
| remarks | Small Text | |

**UI:** "Load Default Items" button (Actions) — pre-populates 12 standard items

---

#### Utility Meter
Configuration record per unit for a utility type (Electricity, Water, Gas, Internet).

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | UMTR-.#### |
| property_unit | Link → Property Unit | Required |
| utility_type | Select | Electricity / Water / Gas / Internet |
| meter_number | Data | |
| unit_of_measure | Select | kWh / Liters / m³ / GB / Units |
| rate_per_unit | Currency | Required |
| customer | Link → Customer | Who is billed |
| utility_item_code | Link → Item | ERPNext Item for invoice line |

**Connections:** Utility Bills
**UI:** "New Utility Bill" and "View Utility Bills" buttons

---

#### Utility Bill
Records meter readings for a billing period and generates a Sales Invoice.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | UBIL-.#### |
| utility_meter | Link → Utility Meter | Required |
| property_unit | Link → Property Unit | Read-only, fetched from meter |
| customer | Link → Customer | Read-only, fetched from meter |
| status | Select | Draft / Invoiced / Paid |
| billing_period_start | Date | Required |
| billing_period_end | Date | Required |
| previous_reading | Float | Required |
| current_reading | Float | Required |
| units_consumed | Float | Read-only — current − previous |
| rate_per_unit | Currency | Read-only, fetched from meter |
| amount | Currency | Read-only — units × rate |
| invoice | Link → Sales Invoice | Read-only, set on invoice generation |

**Automation on validate:** Computes units_consumed and amount; fetches property_unit, customer, rate_per_unit from meter
**UI:** Live calculation of amount; "Generate Invoice" button (Actions); "View Invoice" button when linked
**Whitelisted method:** `generate_invoice(utility_bill_name)` — creates Sales Invoice, sets status to Invoiced

---

### 2.2 Roles

| Role | Access |
|---|---|
| Property Manager | Full CRUD on all property_operations DocTypes |
| Operations User | Read + Create + Write on Issue, Work Order, Maintenance Plan Template, Inspection Checklist, Utility Meter, Utility Bill |
| Tenant | Create + Read own Issues; Read Utility Bills |
| Finance User | Read Utility Meter, Utility Bill |
| Property Owner | Read Inspection Checklist, Issue |

---

## App 3: property_commissions

### 3.1 DocTypes

#### Commission Rule
Configures commission rates per property/sales person combination.

| Field | Type | Notes |
|---|---|---|
| rule_name | Data | Primary key (autoname by field) |
| property | Link → Property | Optional; blank = all properties |
| sales_person | Link → Sales Person | Optional; blank = all sales persons |
| commission_type | Select | Percentage / Flat |
| commission_rate | Float | % of booking amount OR fixed amount |
| effective_from | Date | Optional |
| effective_to | Date | Optional |
| is_active | Check | Default 1 |

**Validation:** rate > 0; if Percentage, rate ≤ 100; effective_to ≥ effective_from

**Priority when multiple rules match:**
1. property + sales_person (most specific)
2. property only
3. sales_person only
4. Global (both blank)

---

#### Commission Entry
Auto-created when a Property Booking is submitted. Read-only; managed by hooks.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | COM-.#### |
| booking | Link → Property Booking | Read-only |
| sales_person | Link → Sales Person | |
| property_unit | Link → Property Unit | Read-only |
| customer | Link → Customer | Read-only |
| commission_date | Date | Booking date |
| booking_amount | Currency | Read-only |
| commission_type | Select | Read-only |
| commission_rate | Float | Read-only |
| commission_amount | Currency | Read-only |
| status | Select | Pending / Settled / Cancelled — read-only |
| commission_rule | Link → Commission Rule | Read-only |
| settlement | Link → Commission Settlement | Read-only |

**Hook — Property Booking on_submit:** `create_commission_entry()` finds applicable rule and creates entry
**Hook — Property Booking on_cancel:** `cancel_commission_entry()` marks entry as Cancelled

---

#### Commission Settlement
Groups Pending commission entries for a sales person and settles them in batch.

| Field | Type | Notes |
|---|---|---|
| naming_series | Select | CSET-.#### |
| sales_person | Link → Sales Person | Required |
| settlement_date | Date | Required |
| status | Select | Draft / Submitted / Paid — read-only |
| total_amount | Currency | Read-only, auto-summed from entries |
| payment_entry | Link → Payment Entry | Linked manually after payment |
| commission_entries | Table → Commission Settlement Entry | |

**Child table — Commission Settlement Entry:**
| Field | Type | Notes |
|---|---|---|
| commission_entry | Link → Commission Entry | Required |
| booking | Link → Property Booking | |
| property_unit | Link → Property Unit | |
| commission_amount | Currency | |
| commission_date | Date | |

**is_submittable:** Yes
**on_submit:** All linked Commission Entries → status = Settled
**on_cancel:** All linked Commission Entries → status = Pending
**Validation:** All entries must belong to same sales_person; all must be in Pending status
**Whitelisted method:** `get_pending_entries(sales_person)` — returns list for "Load Pending Entries" button

---

### 3.2 Roles

| Role | Access |
|---|---|
| Property Manager | Full CRUD + submit/cancel on all property_commissions DocTypes |
| Commission Manager | Create, read, write, submit, cancel Commission Rule / Settlement; read Commission Entry |
| Sales User | Read own Commission Entries |

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
| Project | Optional link on Property; fetched down to Unit, Booking, Allocation, Agreement |

---

## Customer Portal API

Full reference with live responses: **CUSTOMER_PORTAL_API.md**.

Base path `/api/method/property_core.api.portal.<module>.<function>`, token or
session auth, one envelope for every endpoint (`{status, message, data}`). No
endpoint takes a customer parameter — the session user resolves to one Customer
and every query is scoped to it; anything the client names (unit, booking,
invoice, issue) is ownership-checked before it is read.

| Module | Endpoints |
|---|---|
| `meta` | `settings` |
| `profile` | `me`, `update_contact` |
| `dashboard` | `summary` |
| `properties` | `my_units`, `unit`, `projects`, `site_map`, `available_units` |
| `bookings` | `list_bookings`, `booking_details`, `book_unit` |
| `billing` | `charges`, `maintenance_charges`, `utility_bills`, `rent_history`, `outstanding_dues`, `payments`, `invoice`, `payment_schedule` |
| `maintenance` | `work_history`, `schedule`, `inspections` |
| `support` | `issues`, `issue`, `raise_issue`, `add_comment` |
| `documents` | `list_documents` |

`billing.charges` is the unified feed: booking milestones, maintenance invoices,
rent invoices and un-invoiced utility bills merged into one type-tagged list with
a shared `Paid / Overdue / Due Soon / Upcoming` rule.

**Field registry** — payload fields live in `property_core/api/portal/fields.py`,
not inside queries. Any `custom_*` field on Property, Property Unit, Property
Booking, Property Allocation, Property Agreement, Issue or Work Order is exposed
automatically; other fields are one line in `REGISTRY`; another app can extend a
payload via the `portal_extra_fields` hook. Fields missing on a site are dropped
rather than raising, and secrets are blocklisted.

**Not included:** payment-gateway "pay now" calls (gateway methods exist for desk
and webhook flows only) and any document storage of its own — `documents.list_documents`
indexes what is already attached and returns links, not bytes.

The older `property_core.property_core.api.customer_portal.*` methods (11) still
work unchanged and are what the bundled `/customer-portal` page calls.

**Auth:** `property_core.api.auth.*` — `login`, `get_token`, `logout`,
`get_logged_in_user`, `change_password`, `forgot_password` (OTP), `reset_password`.
