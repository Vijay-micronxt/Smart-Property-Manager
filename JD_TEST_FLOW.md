# JD Live — Test Flow

Target site: **jdfarms.storenxt.in** (running `main`)
Branch under test: `main` @ `4d8bd13` — **one app `property_core`, three modules** (Property Core / Property Operations / Property Commissions). There is no separate `property_operations` or `property_commissions` app to install.

Cast: *Priya* (Property Manager) · *Arjun* (Sales User) · *Ravi* (customer, buys plot) · *Meena* (customer, leases flat) · *Suresh* (Operations User)

Legend: `[ ]` to run · **Expect:** pass condition · ⚠ known trap

---

## Act 0 — Setup

### 0.1 Roles (do this first — everything else 404s without it)

Roles are auto-created by Frappe from the DocType permissions; they are **never auto-assigned to users**. No user has them on a fresh site.

- [ ] Give your own user **Property Manager**. Add **Operations User** and **Commission Manager** too if you want to test those screens under a narrower role later.
- [ ] Log out, log back in.

**Expect:** `/app/property-core-settings` opens. If it still says *"Page property-core-settings not found"*, the role didn't stick — that message is what Frappe shows for **no read permission**, not for a missing DocType.

⚠ `System Manager` has **zero** permissions on every property DocType. Only the six payment-gateway DocTypes (Razorpay / Paytm / Mswipe Settings, Razorpay & Mswipe Payment Entry, Razorpay Transaction Log) grant it. Any admin holding only System Manager sees nothing.

### 0.2 Permission matrix (reference — who can see what)

```
Property, Property Unit         PM(RCWD), Sales(R), Ops(R), Owner(R)
Property Booking                PM(RCWDS), Sales(RCWS)
Property Allocation             PM(RCWDS), Sales(R), Finance(R)
Property Agreement              PM(RCWD), Sales(R), Finance(R), Owner(R), Tenant(R)
Payment Plan                    PM(RCWD), Finance(R), Sales(R), Tenant(R)
Payment Plan Template           PM(RCWD)
Property Core Settings          PM(RCW)                      ← single role only
Rent Invoice Log                PM(RCW), Finance(R)
Work Order, Maintenance Plan    PM(RCWD), Ops(RCW)
Inspection Checklist            PM(RCWD), Ops(RCW), Owner(R)
Utility Meter / Bill            PM(RCWD), Ops(RCW), Finance(R), Tenant(R on Bill)
Commission Rule / Settlement    PM(RCWD/S), Commission Manager(RCWD/S)
Commission Entry                PM(R), Commission Manager(R), Sales(R)
Razorpay/Paytm/Mswipe Settings  System Manager(RCW)
```

### 0.3 Property Core Settings

- [ ] `default_company`
- [ ] `security_deposit_account` — a liability account
- [ ] `rent_item_code` — service Item
- [ ] `maintenance_item_code` — service Item (mandatory)
- [ ] `late_fee_item_code`, `enable_late_fees` ✓, `late_fee_grace_days` 5, `late_fee_percentage` 2
- [ ] `whatsapp_enabled` — only if testing OTP over WhatsApp (Act 9)

**Expect:** saves clean. This Single starts completely empty on a fresh site — no defaults are seeded.

### 0.4 Scheduler

- [ ] `bench --site jdfarms.storenxt.in doctor` → scheduler enabled

Otherwise nothing bills on its own; use the manual commands in the cheat sheet.

---

## Act 1 — Inventory (Priya)

- [ ] 1.1 **Payment Plan Template** `JD Standard 5` — 10/20/20/25/25% at offset months 0/1/3/6/12. Change a row to 30% → **Expect:** blocked, "must total 100".
- [ ] 1.2 **Property** `JD Green Acres` — Farmland, company, Active, `payment_plan_template` = above.
- [ ] 1.3 Add 2 amenities + 1 document row. Drop a pin in the Geolocation section.
  **Expect:** map renders, section collapsed by default, coordinates survive reload.
- [ ] 1.4 Items `JD-PLOT-A1`, `JD-FLAT-201` (Maintain Stock **off**).
- [ ] 1.5 **Property Unit** `A-1` — Plot, 2400 sqft, base_price 24,00,000, `item_code = JD-PLOT-A1`.
- [ ] 1.6 **Property Unit** `201` — Flat, base_price 40,00,000, `item_code = JD-FLAT-201`.
- [ ] 1.7 Save another unit numbered `A-1` in the same property → **Expect:** blocked.
- [ ] 1.8 Save a unit with `item_code` blank → **Expect:** warning on the form, not a hard block.

**Expect:** both units `Available` (read-only field), Property form's Units connection = 2.
⚠ `item_code` blank = every invoice generation later fails. Fill it now.

---

## Act 2 — Lead to Booking (Arjun)

- [ ] 2.1 **Lead** for Ravi → convert to **Opportunity**.
- [ ] 2.2 On the Opportunity set **Property** = `JD Green Acres`, **Property Unit** = `A-1`.
  **Expect:** both custom fields present (added by `crm_links.sync_crm_link_fields` on migrate).
- [ ] 2.3 **Customer** `Ravi Kumar` + KYC — Aadhaar, id_number, DOB, PAN, annual income, attach ID scan.
- [ ] 2.4 **Mark KYC Verified** → **Expect:** Verified, date + user stamped, banner green.
- [ ] 2.5 From unit `A-1` → **New Booking** → opens pre-filled.
- [ ] 2.6 Booking: Ravi, amount 2,00,000, sales_person Arjun, opportunity linked. Save + **Submit**.

**Expect on submit:**
- unit `A-1` → `Booked`
- 5 **Payment Plan** rows: 2.4L / 4.8L / 4.8L / 6L / 6L at +0/+1/+3/+6/+12 months
- portal **Website User** auto-provisioned for Ravi (check User list)
- **Commission Entry** — only if Act 8's rule exists first

- [ ] 2.7 Submit a second Booking on `A-1` → **Expect:** blocked at save **and** at submit.
- [ ] 2.8 Cancel it → **Expect:** unit back to `Available`, commission entry (if any) → Cancelled. Re-submit a fresh booking to carry on.

---

## Act 3 — Milestones, invoices, late fees

- [ ] 3.1 Payment Plan #1 → **Generate Invoice**.
  **Expect:** Sales Invoice 2,40,000 to Ravi on `JD-PLOT-A1`; plan → `Invoiced`, button flips to **View Invoice**.
- [ ] 3.2 Generate again → **Expect:** blocked.
- [ ] 3.3 Clear `item_code` on a throwaway unit and generate → **Expect:** clean message, no traceback. Restore.
- [ ] 3.4 Set a plan amount to 0 or negative → **Expect:** blocked.
- [ ] 3.5 Back-date milestone 2 to today, then run the payment-plan scheduler (cheat sheet).
  **Expect:** invoice raised automatically. Run again → **no duplicate**.
- [ ] 3.6 Back-date milestone 3 to 10 days ago, leave Pending, run the billing engine.
  **Expect:** late-fee invoice at 2% on `late_fee_item_code`; plan shows `late_fee_applied` ✓, `late_fee_amount`, `late_fee_invoice`, status `Overdue`. Re-run → no second fee.
- [ ] 3.7 Payment Entry against milestone 1's invoice → **Expect:** outstanding 0. Note whether `payment_status` flips to Paid.

---

## Act 4 — Agreement + security deposit

- [ ] 4.1 **Property Agreement** — Sale Agreement, Ravi, `A-1`, start + signed date, `security_deposit_amount` 1,00,000, attach PDF.
  **Expect:** orange "deposit pending" banner.
- [ ] 4.2 end_date before start_date → **Expect:** blocked.
- [ ] 4.3 **Record Security Deposit** → **Expect:** Journal Entry (Dr bank/cash, Cr deposit liability), posting date = signed_date; flag ✓, JE linked, banner green, **View Deposit Entry** appears.
- [ ] 4.4 Click again → **Expect:** blocked.
- [ ] 4.5 Throwaway agreement, amount blank → **Expect:** blocked, clear message.
- [ ] 4.6 Blank `security_deposit_account` in Settings, retry → **Expect:** blocked, no partial JE. Restore.
- [ ] 4.7 Set status Terminated → **Refund Security Deposit** → **Expect:** JE cancelled, flag cleared.

---

## Act 5 — Sale allocation

- [ ] 5.1 **Property Allocation** — Ravi, `A-1`, **Sale**, booking + agreement linked, start today. **Submit**.
  **Expect:** status `Active`; unit → `Allocated` with `customer` = Ravi; agreement → `Active`; rent fields hidden/empty.
- [ ] 5.2 Cancel → **Expect:** `Terminated`, unit → `Available`. Re-submit fresh to continue.

---

## Act 6 — Lease + recurring rent (Meena)

- [ ] 6.1 Customer `Meena Rao`, KYC verified. Booking on `201`, submit.
- [ ] 6.2 **Property Allocation** — **Lease**, `rent_amount` 25,000, Monthly, `billing_day` 5, start = 1st of last month, end = +11 months. **Submit**.
  **Expect:** unit `201` → `Leased`; `next_billing_date` = 5th of start month.
  ⚠ **If `next_billing_date` is blank, `rent_amount` was empty at submit** — `before_submit` only computes it when rent is set, and a blank one silently never bills. Check this every single time.
- [ ] 6.3 Run the billing engine → **Expect:** invoice 25,000 on `rent_item_code`; one **Rent Invoice Log** row; `next_billing_date` +1 month.
- [ ] 6.4 Run again same day → **Expect:** no duplicate.
- [ ] 6.5 Throwaway Quarterly lease, run engine → **Expect:** date advances 3 months.
- [ ] 6.6 `billing_day` = 31 → **Expect:** blocked (1–28 only).
- [ ] 6.7 Clear `rent_item_code`, run engine → **Expect:** Rent Invoice Log row `Failed` with `error_log`; **other allocations still bill**. Restore.
- [ ] 6.8 Back-date `end_date` to yesterday, run engine → **Expect:** allocation auto-expires, no more invoices.
- [ ] 6.9 **Renew Lease** on an active lease — +12 months, 5% escalation → **Expect:** end_date updated, rent 26,250. Try on the Sale allocation → **Expect:** blocked.

---

## Act 7 — Maintenance / society charges

- [ ] 7.1 **Maintenance Plan Template** `JD Society Monthly`:
  - month 1, "Society Fee", 2,000
  - month 2, "Water Charge", 800, `item_code` override = different Item
  - `repeat_every_n_months` 1, `repeat_amount` 2,000
- [ ] 7.2 On unit `201`: template assigned, `maintenance_start_date` = 3 months ago, `pause_maintenance` off.
- [ ] 7.3 Run the maintenance scheduler → **Expect:** one **submitted** Sales Invoice per due period; row descriptions and Item overrides respected; each invoice carries `property_unit` + `maintenance_period`.
- [ ] 7.4 Run again → **Expect:** zero new invoices (period dedupe).
- [ ] 7.5 Reload unit `201` → **Expect:** **Maintenance Billing History** table with Period / Due Date / Amount / Paid / Outstanding / Status + Total Billed / Total Outstanding.
- [ ] 7.6 Pay one maintenance invoice, reload → **Expect:** that row updates (live read from invoices, not stored).
- [ ] 7.7 Tick `pause_maintenance`, advance a period, run → **Expect:** no invoice. Untick → resumes.
- [ ] 7.8 Row with `fixed_due_date` → **Expect:** billed on that exact date.
- [ ] 7.9 Clear `maintenance_item_code` in Settings → **Expect:** mandatory error.

---

## Act 8 — Commissions

> Run 8.1 **before** Act 2 if you want the commission entry on Ravi's booking.

- [ ] 8.1 **Commission Rule** `JD Global 2%` — property blank, sales_person blank, Percentage 2, active.
- [ ] 8.2 **Commission Rule** `JD Acres Arjun` — property `JD Green Acres`, sales_person Arjun, Percentage 3.
- [ ] 8.3 Rate 150% → **Expect:** blocked. `effective_to` < `effective_from` → **Expect:** blocked.
- [ ] 8.4 Submit a booking for Arjun on a `JD Green Acres` unit → **Expect:** Commission Entry created, read-only, Pending, and it picks the **3%** rule (property+person beats global) — check the `commission_rule` link.
- [ ] 8.5 Booking on a different property → **Expect:** falls back to 2% global.
- [ ] 8.6 Cancel a booking with an entry → **Expect:** entry → `Cancelled`.
- [ ] 8.7 **Commission Settlement** for Arjun → **Load Pending Entries** → **Expect:** only Arjun's Pending entries; `total_amount` auto-sums.
- [ ] 8.8 Add another person's entry → **Expect:** blocked. Add a Settled one → **Expect:** blocked.
- [ ] 8.9 **Submit** → **Expect:** entries → `Settled`, each links back via `settlement`.
- [ ] 8.10 **Cancel** → **Expect:** entries revert to `Pending`.
- [ ] 8.11 Link a Payment Entry in `payment_entry` → **Expect:** saves (disbursement is manual by design).

---

## Act 9 — Customer auth + portal (new on `main`, needs the most attention)

`api/auth.py` is token-based: `Authorization: token <api_key>:<api_secret>`, base `/api/method/property_core.api.auth.<fn>`. No desk session, no cookies.

- [ ] 9.1 Customer login → **Expect:** returns api_key/api_secret pair.
- [ ] 9.2 OTP password reset. With `whatsapp_enabled` ✓ and the customer's `mobile_no` set → **Expect:** OTP goes out via the WhatsApp Message DocType. Unset mobile_no → **Expect:** clean fallback, no crash.
- [ ] 9.3 Profile read/update with the token.
- [ ] 9.4 **Wrong/expired token → Expect: 403.** Do not skip this.
- [ ] 9.5 Portal data APIs as Ravi — `customer_portal_get`, `get_outstanding_dues`, `get_payment_history`, `get_unit_details`, `get_rent_history`, `get_utility_bills`, `get_inspection_reports`, `get_maintenance_requests`.
  **Expect:** each returns only Ravi's own records.
- [ ] 9.6 **Repeat 9.5 as Meena with Ravi's document IDs.** **Expect:** every one refuses. This is the single most important security check in the whole run — website users have no doctype permissions, so these functions' own customer-scoping *is* the boundary.
- [ ] 9.7 `raise_issue` from the portal — subject, description, unit `A-1`.
  **Expect:** Issue created, `via_customer_portal` ✓, `property_unit` set, `raised_by` = Ravi's email, status Open.

⚠ The plot-layout editor and the `/customer-portal` web page are **not on `main`** — they live on the `property_customization` branch and are not deployed to JD. Skip anything layout-related this round.

---

## Act 10 — Payment gateways (new on `main`)

Razorpay, Paytm and Mswipe are all wired to `mark_payment_plan_paid`.

- [ ] 10.1 Configure each Settings DocType in **test/sandbox mode only**. `System Manager` is the role that can open these.
- [ ] 10.2 Generate a payment link for an outstanding milestone.
- [ ] 10.3 Pay in sandbox → **Expect:** webhook fires, Payment Entry created with correct company-currency fields, milestone marked paid, gateway log row written.
- [ ] 10.4 Replay the same webhook → **Expect:** no double Payment Entry.
- [ ] 10.5 Failed/cancelled payment → **Expect:** no Payment Entry, milestone untouched.
- [ ] 10.6 Check `Razorpay Transaction Log` / `Mswipe Payment Entry` / `Paytm` records for the trail.

⚠ Never point these at live gateway credentials during UAT.

---

## Act 11 — Issue → Work Order (Suresh)

- [ ] 11.1 Open Ravi's Issue → **Expect:** **Create Work Order** button present.
- [ ] 11.2 Click → Work Order pre-linked to Issue + unit. Fill description, assigned_to, vendor, scheduled_date, estimated_cost. Save.
  **Expect:** `Issue.work_order` set (read-only); Issue still **Open**; button becomes **View Work Order**.
- [ ] 11.3 Draft → Assigned → In Progress, saving each time → **Expect:** Issue stays **Open** (dispatch states are not mirrored).
- [ ] 11.4 Status **Completed** + actual_cost → **Expect:** `completed_date` auto-filled; Issue → **Resolved** with the Work Order description copied into `resolution_details`.
- [ ] 11.5 Standalone Work Order (Issue blank) on unit `201` → **Expect:** saves fine.
- [ ] 11.6 Portal as Ravi → **Expect:** ticket shows Resolved.

---

## Act 12 — Inspections & utilities

- [ ] 12.1 **Inspection Checklist** — `201`, Move-In, today, inspector Suresh → **Load Default Items** → **Expect:** 12 rows.
- [ ] 12.2 Mark a couple Minor/Major with remarks, overall Good, status Completed.
- [ ] 12.3 **Utility Meter** — `201`, Electricity, kWh, rate 8, customer Meena, `utility_item_code`.
- [ ] 12.4 **New Utility Bill** — prev 1000, current 1350 → **Expect:** `units_consumed` 350, `amount` 2,800 compute live; unit/customer/rate fetched read-only.
- [ ] 12.5 **Generate Invoice** → **Expect:** Sales Invoice 2,800 to Meena; bill → `Invoiced`.
- [ ] 12.6 current < previous → **Expect:** rejected or clearly flagged (record what actually happens).
- [ ] 12.7 Meter → **View Utility Bills** → **Expect:** bill listed.

---

## Act 13 — Roles (one user per role, no extras)

- [ ] 13.1 **Sales User** — creates/submits Bookings; reads Units/Allocations/Payment Plans; **cannot** open Commission Rule, Settings, Work Order.
- [ ] 13.2 **Finance User** — reads Allocations, Payment Plans, Rent Invoice Log, Utility; **cannot** create Bookings.
- [ ] 13.3 **Operations User** — Work Order, Maintenance Plan, Inspection, Utility; **cannot** touch Bookings/Allocations/Commissions.
- [ ] 13.4 **Property Owner** — read-only Property, Unit, Agreement, Inspection.
- [ ] 13.5 **Tenant** — own Agreements + Payment Plans + Utility Bills only.
- [ ] 13.6 **Commission Manager** — full Rule/Settlement, read-only Entry.
- [ ] 13.7 **Property Manager** — everything.

---

## Cross-cutting

- [ ] C.1 Customer, Sales Invoice, Issue, Opportunity, Lead forms open with **zero console errors**.
- [ ] C.2 `bench --site jdfarms.storenxt.in migrate` runs clean (the 5 mswipe patches included).
- [ ] C.3 **No notifications fire from app code.** WhatsApp/SMS/email stays Server Script territory — except the Act 9.2 OTP path, which is app code. Anything else going out means something is wired that shouldn't be.
- [ ] C.4 Walk JD's old site-level Server Scripts / Custom Fields and tick each against an act above. Anything with no home here is a **gap to log**, not a bug.
- [ ] C.5 Error Log holds no `property_*` tracebacks at the end.

---

## Scheduler cheat sheet

```bash
# milestone auto-invoicing
bench --site jdfarms.storenxt.in execute property_core.property_core.utils.payment_plan_billing.run_daily_payment_plan_billing

# rent billing + late fees
bench --site jdfarms.storenxt.in execute property_core.property_core.utils.billing_engine.run_daily_billing

# recurring maintenance billing
bench --site jdfarms.storenxt.in execute property_core.property_operations.utils.maintenance_billing.run_daily_maintenance_billing
```

---

## Open items to raise, not test around

1. **`System Manager` has no access to any property DocType.** Every admin needs Property Manager assigned by hand. Worth a code change adding System Manager to the property DocTypes' permissions, the way the gateway DocTypes already do.
2. **`fixtures` in `hooks.py` is dead** — there is no `fixtures/` directory in the repo, so nothing is ever imported from it. Roles come from Frappe's `make_module_and_roles()` instead. Either export the fixtures or drop the declaration.
3. **Blank `rent_amount` silently disables lease billing** (Act 6.2). No warning at submit.
