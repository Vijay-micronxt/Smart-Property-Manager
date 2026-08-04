# JD Test Run — 2026-08-03

**Story:** TP-TEST-1 walks JD's BRD flow end to end — Lead → Project → Booking → Installments → Maintenance → Possession — with TP-TEST-2 alongside as a lease tenant, used to prove customers cannot see each other's data.

**Where it ran:** local `jd.site`, on branch `property_customization` (= `origin/main` `4d8bd13` + the ported layout work). Same code JD live runs.

**Why not on jdfarms.storenxt.in:** the JD MCP token holds only read-level roles (Sales User / Finance-Tenant class) — it cannot create a Property, open Property Core Settings, or touch Work Order / Commission Rule. Writing a full test dataset into a production ERP was also not something to do unasked. Re-running this on live needs either an elevated token or a manual pass with [JD_TEST_FLOW.md](JD_TEST_FLOW.md).

**Result: 100 checks — 86 passed, 14 failed.** Of the failures, 6 were my own test-harness mistakes (fixed and re-run green). **8 are real product defects**, listed first below.

---

## Defects found

### D1 — Every invoice except maintenance is left in Draft ⚠ highest impact

`Payment Plan.generate_invoice()`, the payment-plan scheduler, `apply_late_fees()`, `_create_rent_invoice()` and `Utility Bill.generate_invoice()` all call `invoice.insert()` and never `submit()`. Only `maintenance_billing._create_invoice_if_new()` does `insert()` + `submit()`.

Observed:

| Invoice | Source | docstatus |
|---|---|---|
| SINV-26-00026 (₹2,40,000 milestone) | manual Generate Invoice | **0 Draft** |
| SINV-26-00027 (₹4,80,000 milestone) | payment-plan scheduler | **0 Draft** |
| SINV-26-00030 (₹9,600 late fee) | billing engine | **0 Draft** |
| SINV-26-00035 (₹25,000 rent) | billing engine | **0 Draft** |
| SINV-26-00036 (₹2,800 utility) | Utility Bill | **0 Draft** |
| SINV-26-00031..34 (maintenance) | maintenance scheduler | 1 Submitted |

Consequence: the milestone's `payment_status` flips to `Invoiced` while nothing has posted to the ledger — no receivable, no outstanding, and a Payment Entry cannot be made. Test 4.8 failed exactly there:

```
ValidationError: Sales Invoice SINV-26-00026 must be submitted
```

Someone has to open and submit every milestone, rent and late-fee invoice by hand, forever. Either submit them in code like maintenance does, or make it a setting — but the two halves of the app should not disagree.

### D2 — Security deposit is completely broken

`record_security_deposit()` sets `reference_type = "Property Agreement"` on both Journal Entry Account rows. ERPNext's `Journal Entry Account.reference_type` is a Select with a fixed option list that has no such option:

```
ValidationError: Row #1: Reference Type cannot be "Property Agreement". It should be one of
"", "Sales Invoice", "Purchase Invoice", "Journal Entry", "Sales Order", ... "Bill of Entry"
```

The JE is never created, so the whole deposit feature — record, view, refund — is dead on stock ERPNext v15. Fix: drop `reference_type`/`reference_name`, or add "Property Agreement" to the Select via a Property Setter on install.

### D3 — Zero-amount milestone passes validation

```python
def validate_amount(self):
    if self.amount and self.amount <= 0:     # 0 is falsy — check never runs
        frappe.throw(_("Amount must be greater than zero"))
```

`amount = 0` saved without complaint. Only negatives are caught. A ₹0 milestone will happily generate a ₹0 invoice. Should be `if self.amount is None or flt(self.amount) <= 0`.

### D4 — `get_maintenance_requests` crashes for every customer

```
OperationalError: (1054, "Unknown column 'resolution_date' in 'SELECT'")
```

The query selects `resolution_date` from Issue; that field does not exist on ERPNext v15's Issue (`frappe.get_meta("Issue").get_field("resolution_date")` → None). Any portal customer opening their tickets list gets a 500. Everything else about the ticket flow works — it's just this one field.

### D5 — Portal user provisioning is a silent no-op

`ensure_portal_user()` looks for a Contact linked to the Customer and reads `Contact.email_id`. No Contact, or a Contact whose denormalized `email_id` is empty → the function returns quietly. No error, no log, no user. The Customer's own email/mobile are never used.

`HOW_TO_USE.md` §3 says "On booking, a portal user is auto-provisioned for the customer — no separate manual step". In this run the booking submitted cleanly and created nothing. Only after a Contact with a populated `email_id` was created did it work, producing `tp.test1@example.com` as a Website User.

### D6 — A Lease with blank `rent_amount` silently never bills

`before_submit` computes `next_billing_date` only `if self.allocation_type in RECURRING_TYPES and self.rent_amount`. Submitting a Lease with rent left blank gives:

```
ALLOC-0005  rent=0.0  next_billing_date=None  status=Active
```

An Active lease that the billing engine will skip forever, with nothing on screen to say so. This is the same state the pre-existing `ALLOC-0003` on this site is stuck in. Either make `rent_amount` mandatory for Lease/Rental, or warn at submit.

### D7 — `raise_issue` never sets `via_customer_portal`

Issue is created correctly (`ISS-2026-00001`, status Open, right unit, right customer, `raised_by` = the portal user) but `via_customer_portal = 0`. `FEATURES.md` lists it as a portal marker. Staff cannot tell portal-raised tickets from desk-raised ones.

### D8 — Agreement date validation raises a raw TypeError

`property_agreement.py:11` compares `self.end_date < self.start_date` without `getdate()`:

```
TypeError: '<' not supported between instances of 'str' and 'datetime.date'
```

It does block the save, but with a Python error instead of "End Date cannot be before Start Date". `property_allocation.py` wraps the same comparison in `getdate()` — this one was missed.

---

## The story, act by act

### Act 1 — Priya sets up the project ✅
Payment Plan Template `TP Installment Plan` — 10/20/20/25/25 at months 0/1/3/6/12. A 60%-total template was **blocked** ("Milestone percentages must total 100%. Current total: 60%").
Property `TP Test Township` (Township, 50,000 sqft, 2 amenities, 1 RERA document row). Units `A-1` (Plot, 2,400 sqft, ₹24,00,000, item TP-PLOT-A1) and `201` (Flat, ₹40,00,000, item TP-FLAT-201). Both landed `Available`.
A second `A-1` was **blocked** — "Unit Number A-1 already exists for Property TP Test Township".

### Act 2 — Lead becomes a customer ✅
Lead `CRM-LEAD-2026-00007` → Opportunity `CRM-OPP-2026-00003`, carrying `property = TP Test Township` and `property_unit = UNIT-0008` on the CRM link fields.
Customer **TP-TEST-1** created with full KYC (Aadhaar, DOB, PAN, occupation, annual income) and marked Verified — date and verifier stamped.
Commission Rules seeded first: `TP Global 2pct` (blank/blank) and `TP Township Agent 3pct` (this property + this agent). A 150% rule was **blocked**.

### Act 3 — Booking ✅
`BKG-0007` submitted. Unit `A-1` → **Booked**.
Five installments generated exactly on plan:

| Milestone | Amount | Due |
|---|---|---|
| On Booking | ₹2,40,000 | 2026-08-03 |
| On Agreement | ₹4,80,000 | 2026-09-03 |
| On Foundation | ₹4,80,000 | 2026-11-03 |
| On Slab | ₹6,00,000 | 2027-02-03 |
| On Possession | ₹6,00,000 | 2027-08-03 |

`COM-0001` auto-created — and it picked the **3% township+agent rule over the 2% global one** (₹6,000 on a ₹2,00,000 booking). Rule priority works.
A second booking on `A-1` was **blocked**: "Property Unit UNIT-0008 is not available. Current status: Booked".
Portal user: **nothing created** — see D5.

### Act 4 — Installments and money ⚠
Milestone 1 → invoice `SINV-26-00026`, ₹2,40,000, on item TP-PLOT-A1. A second attempt was **blocked** ("Invoice already generated for this milestone").
Scheduler auto-invoiced a back-dated milestone 2 and, re-run, created **zero duplicates**.
Late fee: milestone 3 back-dated 10 days → ₹9,600 (2% of ₹4,80,000) on TP-LATEFEE, plan flipped to `Overdue` with `late_fee_applied`, `late_fee_amount`, `late_fee_invoice` all set. Re-run charged **nothing extra**.
Zero-amount milestone — **not blocked** (D3). Payment Entry — **failed**, invoice still Draft (D1).

### Act 5 — Agreement and deposit ❌
`AGMT-0002` created, Sale Agreement, ₹1,00,000 deposit pending. Backwards dates blocked, but via a TypeError (D8). Recording the deposit **failed outright** (D2).

### Act 6 — Possession ✅
`ALLOC-0004` (Sale) submitted → unit `A-1` **Allocated** with `customer = TP-TEST-1`, and the linked agreement flipped to **Active**.

### Act 7 — Maintenance / society charges ✅ (the cleanest module)
Template `TP Society Monthly` — month 1 "Society Fee" ₹2,000, month 2 "Water Charge" ₹800 on the TP-WATER item override, then repeat ₹2,000/month. Assigned to `A-1` starting 3 months back. One run produced exactly four **submitted** invoices:

```
SINV-26-00031  ₹2,000  2026-05   (Society Fee, default item)
SINV-26-00032    ₹800  2026-06   (Water Charge, override item)
SINV-26-00033  ₹2,000  2026-07   (repeat cycle)
SINV-26-00034  ₹2,000  2026-08   (repeat cycle)
```

Re-run: **0 extra**. `pause_maintenance` on, period advanced, re-run: **0 invoices**. Descriptions, per-row item overrides and the repeat cadence all behaved.

### Act 8 — TP-TEST-2 leases flat 201 ✅ (except D6)
`ALLOC-0006` — Lease, ₹25,000/month, billing day 5, from the 1st of last month. Unit → **Leased**, `next_billing_date = 2026-07-05`.
Billing engine → `RINV-0001` ("Jul 2026") with invoice `SINV-26-00035`, `next_billing_date` advanced to 2026-08-05. Re-run: **0 extra logs**.
`billing_day = 31` **blocked** (1–28).
Renew Lease +12 months with 5% escalation → end 2028-07-03, rent **₹26,250**. On the Sale allocation it was **blocked** ("Only Lease or Rental allocations support renewal").
Blank-rent lease: silently unbillable (D6).

### Act 9 — Complaint to resolution ✅ (except D4)
TP-TEST-1 raised `ISS-2026-00001` "Water leakage in bathroom" from the portal — right unit, right customer, `raised_by` = portal user, status Open.
Raising an Issue **against TP-TEST-2's unit was refused**: "Selected unit does not belong to your account".
`WO-0003` created from it — `Issue.work_order` set immediately, Issue stayed **Open** through Assigned and In Progress. On **Completed**: `completed_date` filled and the Issue flipped to **Resolved** with `resolution_details = "Replace bathroom pipe joint"`. Exactly as designed — dispatch states are not mirrored.
Standalone Work Order with no Issue: fine.
Portal ticket list: **crashes** (D4). The dashboard's own `issues` block does show it.

### Act 10 — Inspection and utilities ✅
Inspection `INS-0001` (Move-In) loaded **12 default items**. Utility Meter `UMTR-0001` (Electricity, ₹8/kWh). Bill `UBIL-0001`: 1350 − 1000 = **350 kWh → ₹2,800**, customer auto-fetched. Invoice `SINV-26-00036` ₹2,800 (Draft — D1). A reading lower than the previous was **blocked**.

### Act 11 — Portal and isolation ✅
As TP-TEST-1: `customer_portal_get` returned 1 booking, 1 unit, 1 agreement. `get_outstanding_dues`, `get_payment_history`, `get_unit_details`, `get_utility_bills`, `get_rent_history`, `get_inspection_reports` all returned own-scoped data.
**The isolation check passed**: TP-TEST-1 calling `get_unit_details` on TP-TEST-2's unit was refused — "Selected unit does not belong to your account". Same refusal on `raise_issue`.

### Act 12 — Commission settlement ✅
`CSET-0001` loaded TP Test Agent's pending entries, totalled **₹6,000**, submitted → entry **Settled**. Cancelled → entry back to **Pending**.

### Act 13 — Roles ✅ all eight

```
role                 Property  Unit  Booking  Alloc  Settings  PaymentPlan  WorkOrder  MaintPlan  UtilBill  CommRule  CommEntry
Property Manager     RC        RC    RC       RC     RC        RC           RC         RC         RC        RC        R-
Sales User           R-        R-    RC       R-     --        R-           --         --         --        --        R-
Operations User      R-        R-    --       --     --        --           RC         RC         RC        --        --
Finance User         --        --    --       R-     --        R-           --         --         R-        --        --
Commission Manager   --        --    --       --     --        --           --         --         --        RC        R-
Property Owner       R-        R-    --       --     --        --           --         --         --        --        --
Tenant               --        --    --       --     --        R-           --         --         R-        --        --
System Manager       --        --    --       --     --        --           --         --         --        --        --
```

Every role behaved as designed — and the last row is the earlier "Page not found" mystery in one line: **System Manager has no access to anything.**

---

## Setup notes worth carrying to live

- **HSN/SAC is mandatory** on this site (india_compliance) — every Item needs `gst_hsn_code` or it won't save. Used `997213`.
- `Property Document.document_type` accepts only: Layout Plan, Approval Letter, Encumbrance Certificate, Title Deed, Registration, NOC, Other.
- The security deposit account must **not** be of type Receivable/Payable — those demand a Party on the JE row and `record_security_deposit()` sets one only on the debit side.
- Property Core Settings starts empty. Nothing is seeded.

## Test data left on jd.site

Customers TP-TEST-1 / TP-TEST-2 · Property `TP Test Township` (units A-1, 201, TRAP-1) · BKG-0007 · ALLOC-0004/0005/0006 · AGMT-0002 · 5 payment plans · 7 Sales Invoices for TP-TEST-1 · RINV-0001 · ISS-2026-00001 · WO-0001/0002/0003 · INS-0001 · UMTR-0001 · UBIL-0001 · COM-0001 · CSET-0001 · 8 role users `tp.role.*@example.com`.

## Suggested fix order

1. **D2** security deposit — feature is entirely dead
2. **D1** draft invoices — every rupee of billing needs manual submission
3. **D4** portal ticket list 500
4. **D5** portal user silent no-op
5. **D6** blank-rent lease
6. **D3**, **D7**, **D8** — small, safe one-liners
