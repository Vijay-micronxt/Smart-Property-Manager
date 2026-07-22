# property_core — Improvement TODO

Compiled after manual testing on `jd.site` (frappe + erpnext + property_core). Tracks bugs, design gaps, and missing features before this app can replace/extend what's already built on JD.

## Bugs (breaking)

- [ ] **`Item Plot not found` on invoice generation.** `payment_plan.py::generate_invoice()` sets `item_code = unit.unit_type` ("Plot", "Flat", ...) but no matching Item record is ever created anywhere in the app. Sales Invoice insert fails at `get_item_details()`. Confirmed: this is an app code bug, not related to JD server scripts.
- [ ] **No UI trigger for `generate_invoice()`.** Zero `.js` files in the entire app — no client scripts, no buttons. Payment Plan → Invoice conversion currently only callable via `bench console`.

## Design gaps

- [ ] **Property Unit should map to an Item, not just carry a `unit_type` label.** Needed so native ERPNext Sales Order/Sales Invoice/pricing/tax flow works without workarounds. Matches the pattern already used on JD (Plot = Item). Proposed: auto-create/sync a matching Item on Property Unit save (1:1), keep price/description in sync.
- [ ] **Payment Plan milestone % (10/20/20/25/25) is hardcoded** in `allocation_engine.py`. Needs to be configurable per Property/per client — not every client wants the same construction-linked split. Evaluate whether ERPNext's native Payment Terms Template can replace the custom Payment Plan doctype outright (open question, discuss before building).
- [ ] **Property + Property Unit as two mandatory doctypes** forces creating a project record before every single unit. Not every client needs project-level grouping. Simplify — make Property optional, or collapse into a single doctype with an optional parent link.
- [ ] Property geo-location field/UI needs real design work, currently raw.

## Missing entirely (JD already has these)

- [ ] Maintenance charges — recurring monthly per-unit billing. This is a **separate concern from Payment Plan** (one-time construction-linked installments vs. recurring monthly charges) — do not conflate the two. Port the schedule+repeat-rule pattern from JD into `property_operations` (currently an empty stub).
- [ ] Customer portal booking flow (JD has `customer_portal_book_plot`).
- [ ] WhatsApp/SMS reminders for installments and maintenance dues.
- [ ] Any scheduler/cron jobs.
- [ ] Commission tracking (`property_commissions` stub is empty — hooks.py only).
- [ ] Real test coverage — all existing tests are empty `pass` stubs.
- [ ] Permission rules — roles exist as fixtures (Property Manager, Sales User, Operations User, Finance User, Commission Manager) but no actual DocType permissions wired to them.

## Feature ideas for a seamless end-to-end flow

- [ ] Extend the existing Lead → Opportunity → Booking → Allocation → Agreement → Payment → Possession chain (Booking already links Opportunity — keep that thread going).
- [ ] Unit "Hold" state with expiry, before a formal Booking — auto-release if not confirmed in time. Extend `availability_engine.py`'s state machine.
- [ ] Cancellation/refund rules based on amount already paid.
- [ ] Possession/handover checklist (snagging list) — track physical possession date vs. paper allocation date.
- [ ] Unit transfer/resale flow — booking reassigned to a different customer.
- [ ] Dashboards/reports — project-wise inventory funnel (available/booked/sold), overdue collections.
- [ ] Home loan/subvention tracking — stage-wise disbursement tied to Payment Plan milestones.
