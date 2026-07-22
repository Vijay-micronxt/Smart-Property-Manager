# Global Real Estate App — Module-wise Build Plan

## Context

Goal: turn `property_core` (currently a thin, buggy skeleton — 6 doctypes, no automation, one confirmed bug) into a standalone, installable Frappe app that covers the full real estate business lifecycle and can be dropped onto **any** client's ERPNext, not just JD.

Why standalone app, not server scripts (JD's current approach): JD's real estate logic (53 Server Scripts) is proven in production but lives entirely as customization glued onto ERPNext's own doctypes (Item, Sales Order, Project, CRM Lead). That's fine for one site, but it means every new client needs the same 53 scripts re-created by hand and risks colliding with whatever else is already on their Item/Sales Order. A real app with its own doctypes installs cleanly and ships the logic in version control.

Approach: keep `property_core`'s clean custom-doctype design (Property, Property Unit, Booking, Allocation, Agreement, Payment Plan), but re-implement the business logic by porting the *proven* patterns already validated on JD — not copy-pasting JD's server scripts (they're tied to Item/Sales Order), but rebuilding the same behavior against property_core's own doctypes. Gaps neither app currently covers (commission, possession, reporting, compliance) get built fresh.

Reference material already gathered this session:
- Full `property_core` code read: `vendor/Smart-Property-Manager/property_core/` (doctypes, `availability_engine.py`, `allocation_engine.py`)
- Full JD Server Script inventory via MCP (53 scripts) — which doctype each hooks into and what it does
- Existing `TODO.md` on the `real-estate-enhancement` branch — bugs/gaps already logged

This plan sequences the work module by module. Each module lists: doctypes/fields needed, the core automation, concrete build steps, and which existing code (property_core or JD pattern) to build from.

---

## Module 1 — CRM & Lead

**Doctypes**: none new — reuse ERPNext/CRM `Lead`/`Opportunity` (property_core's `Property Booking` already links `opportunity`).

**JD pattern to port** (logic only, not the scripts themselves):
- Duplicate lead detection on create (JD: `CRM Lead Duplicate Notification`)
- Follow-up reminder if lead untouched for N hours (JD: `Lead Follow-up WhatsApp Reminder`, hourly cron)
- Auto task creation on lead assignment (JD: `create a new task based on lead task`)

**Steps**:
1. Add `hooks.py` `doc_events` on `Lead`: `after_insert` → duplicate check (match by phone/email).
2. Add a scheduler event (hourly) in property_core: scan open Leads with no activity in N hours → queue reminder (start with email/log; WhatsApp wiring comes in Module 9).
3. Keep this module thin — Lead/Opportunity → Property Booking is the only hard link property_core needs; don't rebuild all of JD's CRM Lead surface, just the parts feeding into booking.

---

## Module 2 — Project & Inventory (Property / Unit / Layout)

**Doctypes**: `Property` (exists), `Property Unit` (exists) — needs the Item-linkage fix.

**Core fix (already in TODO.md, this is where it belongs)**:
- On `Property Unit` save, auto-create/sync a matching **Item** (1:1). This is the root fix for the `Item Plot not found` bug and is required before Module 4 (Payment/Invoice) can work at all.
- JD reference: `Plot - Sync Selling Price From Rate` (Item, After Save) — mirrors price sync; we need the reverse direction too (Unit → Item creation).

**Steps**:
1. `property_unit.py`: in `validate()` or `on_update()`, if no linked Item exists, create one (`item_code` = unit name or a configurable naming rule), sync `item_name`, `standard_rate` = `base_price`.
2. Add `item` Link field to Property Unit JSON to store the mapping explicitly (don't rely on name-matching).
3. Plot Layout / visual design tool: JD has `Plot Layout - Save` / `Plot Layout - Get Data` APIs (a visual map UI). Out of scope for first pass — flag as a later Module 2b (needs a custom Page/Web Page, not just doctype work).
4. Property (project) level is optional, not mandatory — see Design Decision #1 below.

---

## Module 3 — Sales & Booking

**Doctypes**: `Property Booking` (exists), `Property Allocation` (exists).

**Gaps vs JD's Sales Order handling** (JD handles booking lifecycle more completely):
- No handling for booking **delete** (JD: `Booking Form - Recompute Plot on Delete`) — property_core only handles cancel.
- No validation that the unit actually belongs to the project being booked against (JD: `Booking Form - Validate Plot Project`).
- No enforcement that rate/area are filled before booking confirms (JD: `Booking Form - Require Rate and Area`).

**Steps**:
1. Add `on_trash` hook to `Property Booking` (release unit, mirror `on_cancel` logic in `availability_engine.py`) — currently only `on_cancel`/`on_submit` exist.
2. Add validation in `Property Booking.validate()`: unit's `property` must match booking's declared property (prevents cross-project booking mistakes).
3. Add mandatory-field validation before submit (unit `area`/`base_price` must be set) — cheap safety net, mirrors JD's `Booking Form - Require Rate and Area`.
4. Keep `Property Allocation` as-is structurally; it already mirrors JD's confirm-sale step reasonably well.

---

## Module 4 — Payment & Installments

**Doctypes**: `Payment Plan` (exists) — needs configurability + automation.

**Gaps** (both flagged in TODO.md already):
- Milestone % hardcoded in `allocation_engine.py` (10/20/20/25/25).
- `generate_invoice()` has no UI trigger and depends on Module 2's Item fix to not crash.

**Steps**:
1. Add a `Payment Schedule Template` child-table doctype on `Property` (milestone name, offset months or trigger event, percentage) — replaces the hardcoded `DEFAULT_MILESTONES` list in `allocation_engine.py`. Each Property picks its template (or falls back to a system default).
2. Rewrite `generate_payment_plan()` to read from the Property's template instead of the hardcoded constant.
3. Fix `generate_invoice()` (blocked on Module 2 Item fix) and auto-trigger it — JD's pattern is full-chain automatic (Quotation→Sales Order→Sales Invoice all auto on submit); property_core should auto-generate the Sales Invoice when a Payment Plan milestone's due_date arrives (scheduler) rather than requiring a manual call, with a manual override button for early payment.
4. Add a client script button on Payment Plan for manual "Generate Invoice Now" (closes the "no UI trigger" bug) — this is the one place a `.js` file is actually needed.
5. Payment Plan stays a custom doctype, not replaced by Payment Terms Template — see Design Decision #2 below for why.

---

## Module 5 — Maintenance & Recurring Billing

**Doctypes**: new — `Maintenance Plan Template` + `Unit Maintenance Schedule` (child table), modeled directly on JD's proven `Maintenance Plan Template` / `Plot Maintenance Schedule` (already inspected via MCP — month-wise charge table + `repeat_every_n_months` + `repeat_amount` for post-schedule recurring).

**This is the strongest, most directly portable module** — JD's design here is clean and already production-tested.

**Steps**:
1. Recreate `Maintenance Plan Template` in property_operations (currently the empty stub — this is exactly what it's for) with the same shape: `template_name`, `schedule` (child table: month, amount), `repeat_every_n_months`, `repeat_amount`.
2. Recreate the child doctype (`Unit Maintenance Schedule` — JD calls it `Plot Maintenance Schedule`).
3. Link Property Unit → Maintenance Plan Template (optional field, not every unit needs maintenance billing).
4. Scheduler event (daily/monthly cron): for each unit with an active template, generate the due invoice for the current month if not already generated, mirroring JD's `Plot Maintenance - Generate Invoices & Remind`.
5. Reminder (WhatsApp/email) hook — wire into Module 9's communication layer rather than duplicating.

---

## Module 6 — Documents & Legal

**Doctypes**: `Property Agreement` (exists, minimal).

**Steps**:
1. Keep the simple `Attach` field approach for v1 — JD's Drive-based per-project folder auto-provisioning (`Auto Create Drive Folders on Project`, `Sync Drive Permissions on Project Save`) is powerful but depends on the Frappe Drive app being installed, which not every client will have. Treat Drive integration as an **optional enhancement**, not a core dependency.
2. Add standard document types as a Select field or child table on Property Agreement: KYC, Allotment Letter, Sale Agreement, Sale Deed, NOC, Possession Letter — so multiple documents can attach to one allocation instead of the current single-file field.
3. E-signature integration: out of scope for first pass, flag for later.

---

## Module 7 — Commission & Channel Partner

**Doctypes**: new — this is a clean-slate module (confirmed zero commission logic exists on JD, and `property_commissions` is an empty stub — exactly the gap to fill).

**Steps**:
1. `Commission Rule` doctype: partner/sales person, applies-to (Property or globally), percentage or flat, slab-based option (e.g. different % for cash vs loan-financed).
2. `Commission Entry` doctype: auto-created `on_submit` of `Property Allocation` (or `Property Booking`, decide which event should trigger — Allocation is the "deal confirmed" point, more defensible for commission payout than Booking).
3. Payout tracking: status field (Pending/Approved/Paid), link to Payment Entry once paid.
4. This module has no JD reference to port from — build it clean against property_core's own doctypes from the start.

---

## Module 8 — Possession & Handover

**Doctypes**: new — `Possession Checklist` (child table of inspection items), field on `Property Allocation` for `possession_date`.

**Steps**:
1. Simple checklist child table (item, status, remarks) attached to Allocation.
2. `possession_date` vs `agreement.end_date`/`allocation.start_date` — track paper-allocation-date vs physical-handover-date as two distinct fields (real estate businesses care about this gap).
3. No JD reference — greenfield.

---

## Module 9 — Customer Portal & Communication

**Doctypes**: none new — API layer + portal pages.

**JD reference** (directly portable pattern, 4 proven APIs): `Customer Portal - Get Data`, `Customer Portal - Book Plot`, `Customer Portal - Raise Issue`, `Customer Portal - Maintenance Charges`.

**Steps**:
1. Whitelisted API: portal data fetch (customer's bookings, payment status, maintenance dues) — mirrors `Customer Portal - Get Data`.
2. Whitelisted API: book a unit from portal — mirrors `Customer Portal - Book Plot`, but writes to `Property Booking` instead of `Sales Order`.
3. Whitelisted API: raise a complaint/issue — this is effectively a lightweight ticket system; check if ERPNext's `Issue` doctype (from Helpdesk/Support) can be reused instead of building one from scratch.
4. WhatsApp reminder sender — one shared utility function used by Module 1 (lead follow-up), Module 4 (installment due), Module 5 (maintenance due). Build once, call from three schedulers, rather than three separate integrations.
5. Portal user auto-provisioning on first booking — mirrors JD's `Customer - Create Portal User` / `Booking Form - Create Customer Portal User`.

---

## Module 10 — Reporting & Compliance

**Doctypes**: none new (reports + dashboard).

**Steps**:
1. Inventory status report: units by availability_status, grouped by Property — single query report, cheap to build, high value.
2. Collection aging report: overdue Payment Plan milestones.
3. Sales funnel: Lead → Booking → Allocation conversion counts.
4. RERA / compliance: flagged as a real gap (india_compliance covers GST/e-invoice, not RERA). Scope this only if a client actually needs RERA filing support — don't build speculatively.

---

## Recommended Build Order

Dependencies force most of this order; Module 5 and 9 can run in parallel with 3/4 once Module 2 is done since they're less coupled.

1. **Module 2** (Item-linkage fix) — blocks Module 4 entirely, do this first.
2. **Module 3** (Booking lifecycle gaps) — cheap, high-value correctness fixes.
3. **Module 4** (configurable Payment Plan + working invoice generation) — the app is not usable for real testing until this works end-to-end.
4. **Module 5** (Maintenance) — highest-confidence port from JD, can start as soon as Module 2 lands.
5. **Module 9** (Portal + shared WhatsApp utility) — depends on Modules 3/4/5 existing to have data to expose.
6. **Module 7** (Commission) — independent, can slot in anytime after Module 3.
7. **Module 6, 8, 10** — lower urgency, do after the above are stable.
8. **Module 1** (CRM automation beyond the existing Opportunity link) — lowest priority; ERPNext/CRM already provides base Lead functionality, this is polish.

## Design Decisions (finalized)

**1. Property (project level) — optional, not mandatory.**
Make `Property Unit.property` a non-mandatory Link (`reqd: 0`). Small clients selling one standalone building can leave it blank; multi-phase township clients use it to group units. Additionally, add an optional `erpnext_project` Link field on `Property` → ERPNext's native `Project` doctype, purely opt-in — it unlocks Project's Gantt/task-tracking and (if the client has Frappe Drive) the auto-folder-per-project pattern JD already proved (`Auto Create Drive Folders on Project`). This is additive, not a dependency: `Property` works standalone with zero ERPNext Project involvement if a client doesn't want it.

**2. Payment Plan (custom doctype) — keep it, it is not redundant with Payment Terms Template.**
These solve different problems, confirmed by how each actually works:
- ERPNext's **Payment Terms Template** splits the due amount of *one already-raised* Sales Invoice/Order into dated portions (30/60/90-day terms, or % splits) — it drives one document's Payment Schedule child table. It assumes the invoice already exists.
- Our **Payment Plan** needs to *generate a new, separate Sales Invoice per construction milestone*, raised only when that milestone is actually reached — the invoice for "On Foundation" shouldn't exist until the foundation is done, which is a real-world date that shifts. Payment Terms Template has no mechanism to defer creating additional invoices over time; it only staggers due dates on one.
- ERPNext's `Subscription` doctype (recurring invoice generation) doesn't fit either — it's for fixed-amount recurring billing, not variable percentage-of-price milestones. (This is also why JD built a custom `Maintenance Plan Template` for Module 5 instead of using Subscription — same reasoning applies there.)
- Decision: keep `Payment Plan` as a custom doctype. Build the configurable milestone template (Module 4, step 1) as planned.

**3. Commission trigger point — `Property Allocation` submit, with an optional split.**
Real-world norm: paying commission at Booking is risky because bookings can cancel before the deal is confirmed (customer backs out, fails next installment) — clawing back paid commission is messy. Standard practice is to pay on confirmed sale. Decision: `Commission Entry` auto-creates `on_submit` of `Property Allocation` (the "deal confirmed" event), not Booking. To support firms that pay a partial commission upfront at booking, `Commission Rule` gets an optional split config (e.g., 50% payable on Booking submit, 50% on Allocation submit) rather than hardcoding a single trigger — default behavior with no split configured is 100% on Allocation.

## Immediate Next Action

Commit this plan as `PLAN.md` on the `real-estate-enhancement` branch (alongside the existing `TODO.md`) and push to `origin`, so the module roadmap and design decisions are version-controlled alongside the code they'll produce.

## Verification

- Each module's doctype/logic changes get tested on `jd.site` (already has property_core installed) via `bench --site jd.site console` and Desk UI, same workflow used earlier this session (Property → Unit → Booking → Allocation).
- Maintenance module: cross-check generated invoices/schedule against JD's live `Maintenance Plan Template` behavior (read-only via MCP) to confirm parity.
- No changes land on the `main`/`claude/review-realestate-docs-wlDbf` branches — all work happens on `real-estate-enhancement` (already created and pushed).
