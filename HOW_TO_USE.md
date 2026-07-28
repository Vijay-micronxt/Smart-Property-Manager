# How to Use the System

Plain-language walkthrough of the day-to-day flow across the 3 apps, current as of the 2026-07-23 architecture pass (Issue/Work Order unified, recurring maintenance billing added, plug-and-play uninstall safety). For the full field-by-field reference see `FEATURES.md`; for step-by-step test scripts see `TEST_CASES.md` / `USE_CASES.md`.

---

## 1. The 3 apps, in one line each

- **property_core** — mandatory foundation. Property, Property Unit, Property Booking, CRM links (Lead/Opportunity → Property/Unit), Payment Plan billing, Customer Portal APIs.
- **property_operations** — optional, install on top of property_core. Issue/Work Order dispatch, recurring Maintenance Plan billing, Inspection Checklist, Utility Meter/Bill.
- **property_commissions** — optional. Sales agent Commission Rule → Entry → Settlement.

They depend on each other in one direction only: operations and commissions add fields onto core's (or ERPNext's) doctypes via their own `create_custom_fields()` calls; core never references them back. Each optional app also cleans up after itself on `bench uninstall-app` (`before_uninstall` hooks remove exactly the custom fields it added) — install or remove either optional app and the doctypes it touched revert to their original shape, nothing left behind or broken.

---

## 2. Setting up a property

1. Create a **Property** (the building/project/farmland).
2. Create **Property Unit** records under it (plot/flat/farm parcel) — set `base_price`, `unit_type`, `area`, HSN/SAC if applicable.
3. If this unit will carry recurring maintenance charges (society fee, upkeep, etc.), see §7 below — that's set up per-unit, independent of everything else.

---

## 3. Lead to Booking

1. Leads and Opportunities are ERPNext-native — nothing new to learn there. property_core adds a `property`/`property_unit` field on both so a lead is tied to a real unit from the start.
2. When a customer commits, create a **Property Booking** against the Property Unit.
   - The Booking form shows the unit's property, type, area, and base price directly (read-only, fetched) — no need to open the Property Unit separately to check what's being booked.
3. On booking, a **portal user is auto-provisioned** for the customer (if one doesn't already exist) — no separate manual step to give them portal access.

---

## 4. Getting paid (Payment Plan)

1. Attach a **Payment Plan Template** to the Booking (milestone-based: e.g. 20% on booking, 30% in 3 months, etc.).
2. A daily scheduler (`payment_plan_billing.py`) automatically raises a Sales Invoice for each milestone as it comes due — no manual "Generate Invoice" click needed.
3. What the scheduler does **not** do: send the invoice anywhere (email/WhatsApp/SMS). That's deliberate — see §9.

---

## 5. Customer Portal

Customers log in and can:
- View their own bookings/units (`customer_portal_get` API).
- **Raise a complaint or query** — creates an **Issue** directly (ERPNext's own ticketing doctype; property_core just tags it with the unit). This is the *only* entry point for anything a customer reports, whether it's maintenance-related or a general question — there is no separate "Maintenance Request" doctype.

---

## 6. Handling a complaint (Issue → Work Order)

1. Customer (or staff, on their behalf) raises an **Issue**. Status starts Open.
2. If it needs someone to physically go fix something, staff click **Create Work Order** on the Issue form (only shown once property_operations is installed). This opens a new Work Order pre-linked to that Issue and unit.
3. Work Order tracks the operational side: vendor, scheduled date, cost, its own status (Draft → Assigned → In Progress → Completed).
4. The moment the Work Order is marked **Completed**, the linked Issue automatically flips to **Resolved** with the Work Order's notes copied into `resolution_details`. Nothing else about the Work Order's day-to-day status (Assigned/In Progress) is mirrored onto the Issue — that granularity is for staff dispatch tracking only, the customer just sees Open → Resolved.
5. Not every Work Order needs an Issue behind it — internal/preventive maintenance can be created standalone (leave the Issue field blank).

---

## 7. Recurring maintenance / society charges

This is a **separate concept from complaints** — it's scheduled billing, not something triggered by a customer report. Ported from JD's own proven live-system pattern.

1. Create a **Maintenance Plan Template** — a reusable month-wise charge schedule with an optional "repeat every N months at ₹X" rule so it keeps billing indefinitely without listing every future month by hand.
   - Each schedule row can optionally set its own **Description** (e.g. "Society Fee", "Water Charge" — shown on the invoice line) and its own **Item (override)** (e.g. bill water charges under a different ledger Item). Leave both blank and it just uses the generic default text and Property Core Settings' default Item.
   - The repeat cycle (charges after the listed months run out) always uses the generic default text; it can still override the Item via **Repeat Item (override)**.
2. Set **Maintenance Item Code** once in **Property Core Settings** — this is mandatory, it's the default Item used whenever a row/repeat cycle doesn't specify its own.
3. On the **Property Unit**, set:
   - `Maintenance Plan Template` → the template to use
   - `Maintenance Start Date` → when billing should start counting from
   - (optional) `Pause Maintenance Billing` checkbox to temporarily stop it
4. A daily scheduler auto-creates and submits one Sales Invoice per unit per due period, skipping any period already billed (so re-running it is always safe, never double-bills).
5. Once a template is assigned, the unit's form shows a live **Maintenance Billing History** table — period, due date, amount, paid, outstanding, status, plus a Total Billed / Total Outstanding summary — built from the unit's actual Sales Invoices, not stored/duplicated data.

---

## 8. About WhatsApp / SMS / notifications

**Deliberately not built into any app code.** Every automated event above (invoice generated, Issue raised, Work Order completed, maintenance invoice due, etc.) is a normal Frappe document event — the message layer gets wired via **Server Script** on top, independent of app releases. This means message wording/templates can be changed anytime without a code deploy. If a new "notify on X" need comes up, the hook point (which doctype, which event) already exists; only the Server Script needs to be added.

---

## 9. Inspections & Utilities (property_operations)

- **Inspection Checklist** — periodic property/unit inspection records.
- **Utility Meter** / **Utility Bill** — meter readings and utility billing, independent of the maintenance/complaint flow above.

---

## 10. Commissions (property_commissions)

**Commission Rule** (how much a sales agent earns) → **Commission Entry** (calculated per booking/sale) → **Commission Settlement** (marks it paid, links a `payment_entry`). Disbursement itself (actually running payroll) is not wired to HRMS yet.

---

## 11. Roles at a glance

| Role | Typical use |
|---|---|
| Property Manager | Full access across all 3 apps |
| Operations User | Issue, Work Order, Maintenance Plan Template, Inspection, Utility |
| Finance User | Utility Meter/Bill, invoicing side |
| Property Owner | Read-only Inspection/Issue visibility |
| Tenant / Customer (portal) | Own bookings, own Issues, own utility bills |

---

## 12. Where to look next

- Full field-by-field reference: `FEATURES.md`.
- Step-by-step test scripts: `TEST_CASES.md`.
- End-user scenarios: `USE_CASES.md`.
