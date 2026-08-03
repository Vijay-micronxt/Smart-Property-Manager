# JD Live — TP-TEST Walkthrough

Built on **jdfarms.storenxt.in** on 2026-08-03 with the user's own API token (acting as `tushar@micronxt.com`, which now holds Property Manager). Everything below is real data on the live site.

---

## What exists now

| Step | Record | Detail |
|---|---|---|
| Lead | `CRM-LEAD-2026-00077` | TP TEST, tp.test@example.com, 9800000001, source Walk In |
| Opportunity | `CRM-OPP-2026-00001` | carries `property = TP-Test-Project`, `property_unit = UNIT-0001` |
| Customer | `CUST-2026-00005` | name **TP-TEST**, KYC **Verified**, Aadhaar + PAN filled |
| Contact | `TP-TEST-CUST-2026-00005` | linked to the customer, email set |
| Project (Property) | **TP-Test-Project** | Farmland, 43,560 sqft, Active, 2 amenities, plan template attached |
| Plot 1 | `UNIT-0001` (TP-01) | 1,200 sqft, ₹12,00,000, Item `PLOT-2026-0008` — **Booked** |
| Plot 2 | `UNIT-0002` (TP-02) | 1,500 sqft, ₹15,00,000, Item `PLOT-2026-0009` — **Booked** |
| Installment plan | `TP Test Installment Plan` | 20 / 30 / 25 / 25 % at months 0 / 1 / 3 / 6 |
| Booking 1 | `BKG-0001` | plot TP-01, ₹2,40,000 advance, **Confirmed** |
| Booking 2 | `BKG-0002` | plot TP-02, ₹3,00,000 advance, **Confirmed** |
| Installments | `PP-0001…PP-0008` | 4 per booking, auto-generated |
| Invoice | `ACC-SINV-2026-00004` | ₹2,40,000 — **Draft** |
| Maintenance plan | `TP Test Maintenance Plan` | ₹500 m1, ₹500 m2, ₹1,200 m3 (Annual Water), then ₹500/month forever |
| Settings | Property Core Settings | company + `maintenance_item_code = Plot Maintenance Charge` set. **Late fees left OFF** |

Installments raised automatically the moment each booking was submitted:

```
BKG-0001 (₹12,00,000 plot)          BKG-0002 (₹15,00,000 plot)
  Booking Advance    2,40,000 03 Aug   Booking Advance    3,00,000 03 Aug
  Agreement Signing  3,60,000 03 Sep   Agreement Signing  4,50,000 03 Sep
  Development Stage  3,00,000 03 Nov   Development Stage  3,75,000 03 Nov
  On Registration    3,00,000 03 Feb   On Registration    3,75,000 03 Feb
```

Percentages, amounts and offset months all came off the template correctly.

---

## Question 1 — Do invoices auto-generate?

**The schedule is real and running.** On live:

```
billing_engine.run_daily_billing                    Daily  stopped=0  last run 2026-08-03 00:02:53
maintenance_billing.run_daily_maintenance_billing   Daily  stopped=0  last run 2026-08-03 00:03:06
payment_plan_billing.run_daily_payment_plan_billing Daily  stopped=0  last run 2026-08-03 00:03:08
```

`enable_scheduler = 1`. So yes — every night around 00:03 the system looks for milestones that have come due and raises a Sales Invoice for each, with no one clicking anything.

**But there is a catch, and it matters.** Every invoice from the milestone/rent/late-fee path is created as a **Draft**. Proof from this run — the milestone invoice was generated through the app's own method:

```
ACC-SINV-2026-00004   ₹2,40,000   docstatus=0  → DRAFT, nothing posted
```

A Draft invoice is not in the ledger. No receivable against TP-TEST, no outstanding, and a Payment Entry cannot be recorded against it. Someone has to open each one and hit Submit.

The one exception is **maintenance billing**, which creates *and submits* its invoices. So today the system behaves in two different ways:

| Path | Auto-created? | Auto-submitted? |
|---|---|---|
| Payment plan milestone (nightly) | yes | **no — Draft** |
| Payment plan milestone (button) | yes | **no — Draft** |
| Rent (lease/rental, nightly) | yes | **no — Draft** |
| Late fee (nightly) | yes | **no — Draft** |
| Utility bill | yes | **no — Draft** |
| **Maintenance (nightly)** | yes | **yes — submitted** |

This is a one-line code change in each generator (`invoice.submit()` after insert), or a setting if JD wants a review step. Right now it is neither — it is just inconsistent.

---

## Question 2 — Maintenance: what is the flow, how is it tracked?

### Setup, done once

1. **Property Core Settings → Maintenance Item Code.** Set to the existing `Plot Maintenance Charge` item. This is the invoice line used unless a row overrides it. Mandatory.
2. **Maintenance Plan Template.** A month-wise charge sheet, reusable across plots. Built `TP Test Maintenance Plan`:

   | Month | Description | Amount | Item |
   |---|---|---|---|
   | 1 | Plot Maintenance - Month 1 | ₹500 | default |
   | 2 | Plot Maintenance - Month 2 | ₹500 | default |
   | 3 | Annual Water Charge | ₹1,200 | default |
   | then | repeat every **1** month | ₹500 | default |

   Each row can carry its own description (that text lands on the invoice line) and its own Item, so a water charge can post to a different ledger than the society fee. The repeat block is what keeps it billing after the listed months run out — without it, billing simply stops.

### Per plot

On the Property Unit set three fields:

- **Maintenance Plan Template** → which sheet to use
- **Maintenance Start Date** → the date month 1 counts from
- **Pause Maintenance Billing** → tick to stop temporarily, untick to resume

`UNIT-0001` is enrolled with start date **2026-05-03** (back-dated 3 months on purpose, so tonight's run has something to bill).

### What happens on its own

Every night the maintenance job walks each enrolled, unpaused unit, works out which periods have come due since the start date, skips any period already billed, and raises **one submitted Sales Invoice per new period**. Each invoice carries `property_unit` and `maintenance_period` (e.g. `2026-05`) — that period stamp is what prevents double billing, so re-running is always safe.

Because `UNIT-0001` is back-dated to May, the next run should produce three invoices: **₹500 (2026-05) + ₹500 (2026-06) + ₹1,200 (2026-07)**. Check `TP-Test-Project → UNIT-0001` tomorrow morning.

> If you'd rather not have those three appear, set Maintenance Start Date back to today's date before midnight, or tick Pause Maintenance Billing.

### How it is tracked

Open the Property Unit. Once a template is assigned, the form shows a live **Maintenance Billing History** table:

```
Period | Due Date | Amount | Paid | Outstanding | Status
                              Total Billed / Total Outstanding
```

It is built from the unit's actual Sales Invoices each time the form loads — not a stored copy — so it always matches accounts. Paid/Outstanding move as payments come in.

For a portfolio view instead of one plot: Sales Invoice list, filter on `property_unit` or `maintenance_period`.

### To collect the money

Maintenance invoices are already submitted, so they behave like any normal invoice — Payment Entry against them, and outstanding shows in the customer's ledger. **This is the only billing stream in the app that works end to end today.** Milestone invoices need the Draft problem fixed first.

---

## What broke on live

### Portal login is half-created

After the second booking, the system did create the Website User `tp.test@example.com` (enabled) — but **no Portal User row was linked to the customer**, so the customer still cannot see their own data on the portal.

Cause: JD has **no outgoing email**. Every Email Account on the site has `enable_outgoing = 0`. `ensure_portal_user()` inserts the User with `send_welcome_email: 1`; the welcome mail throws, and the exception aborts the function before the Portal User row is written. Error Log at the exact minute of the run:

```
Unable to send new password notification   2026-08-03 14:10:21
```

The booking's caller wraps this in try/except, so nothing surfaces — the booking submits perfectly and the portal link is quietly missing.

Two things need fixing: `send_welcome_email` should be 0 (or the failure caught inside the function), and the Portal User row should be written before the mail is attempted. Until SMTP is configured on JD, any portal onboarding will hit this.

A second, smaller trap: `ensure_portal_user()` reads `Contact.email_id`. Creating a Contact through the API with an `email_ids` child row leaves that denormalized field **empty** until the Contact is saved again — so on the first booking nothing happened at all. Re-saving the Contact fixed it.

### Security deposit cannot be recorded

Not exercised here because it fails on any ERPNext v15: `record_security_deposit()` stamps `reference_type = "Property Agreement"` on the Journal Entry rows, and ERPNext's Select has no such option. Full detail in `JD_TEST_RUN_2026-08-03.md` (D2).

---

## Site quirks worth knowing

- **Items are named by series** (`PLOT-.YYYY.-.####`), so the `item_code` you type is discarded. The two plot items came out as `PLOT-2026-0008` / `PLOT-2026-0009`. Identify them by `item_name`.
- **Customers are named by series** too — TP-TEST is `CUST-2026-00005`.
- `Property Amenity.amenity_type` only accepts: Basic, Security, Recreation, Commercial, Green, Smart Home.
- Property Core Settings was completely empty before this run. Company and Maintenance Item are now set; **late fees deliberately left off** so no live customer gets charged by accident.

---

## Suggested next steps

1. Fix the Draft-invoice inconsistency — nothing about milestone billing is usable until then.
2. Fix portal provisioning (`send_welcome_email`, ordering), or configure SMTP on JD.
3. Fix the security deposit reference_type.
4. Then decide the real JD numbers: actual maintenance amounts, actual installment split, and whether late fees should be on.

Cleanup, if you want the test data gone: cancel `BKG-0001`/`BKG-0002` (releases both plots), then delete `PP-0001…0008`, `ACC-SINV-2026-00004`, both Property Units, `TP-Test-Project`, `CUST-2026-00005`, `CRM-LEAD-2026-00077`, `CRM-OPP-2026-00001`, both plot Items and the two templates.
