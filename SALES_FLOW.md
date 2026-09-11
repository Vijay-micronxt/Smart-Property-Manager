# Sales flow: enquiry to possession

The short version of who owns what, and why the old flow kept breaking.

## The model

A customer does not buy a **Property**. A Property is the development — a
township, an apartment block, a farmland project. What gets sold is a
**Property Unit**: one plot, one flat, one villa. Everything about money
therefore hangs off the unit, not the property.

| Thing | DocType | Created when |
|---|---|---|
| Construction project (costing, Gantt) | `Project` (ERPNext) | Optional. Before sales open. |
| The development | `Property` | Before sales open |
| The sellable unit | `Property Unit` | Before sales open, in bulk |
| Raw enquiry | `Lead` (ERPNext) | Someone calls, walks in, fills a form |
| Qualified requirement | `Opportunity` (ERPNext) | Lead is worth working |
| The deal | `Property Booking` | Customer commits to a unit |
| Instalments | `Payment Plan` | Automatically, on booking submit |
| The bill | `Sales Invoice` | Automatically, as each instalment falls due |
| Possession | `Property Agreement` + `Property Allocation` | On handover |

### Where Project attaches

On **Property only**. `Property Unit.project` is fetched read-only from its
property. An editable project on the unit is a second source of truth waiting
to disagree with the first.

Note the direction: a Project is **not** created per deal. Inventory comes
first, opportunities point at it. What the team wants from "show me this
project's opportunities" is visibility, and that is a Connections tab, not a
creation step — Project, Lead, Opportunity and Customer all now list the
property documents.

### Where Opportunity attaches

`Opportunity.custom_property` is **mandatory**; `custom_property_unit` is
optional, because at this stage a prospect often wants "a 30x40 in phase 2"
without having picked the plot. The requirement fields (`custom_unit_type`,
`custom_budget`, `custom_required_area`, `custom_preferred_facing`) carry
across from Lead automatically — same fieldnames, so Frappe's mapper copies
them.

### Where the payment plan attaches

To the **booking**, which points at exactly one unit. The template is resolved
in this order:

1. `Property Booking.payment_plan_template` — this deal
2. `Property Unit.payment_plan_template` — this unit type
3. `Property.payment_plan_template` — the development's default
4. the built-in five-milestone default

Amounts are a percentage of `Property Booking.total_price` — the **agreed**
value — not the unit's list price, so a negotiated deal bills what was agreed.

## The flow

```
SETUP (once)
  Project (optional) -> Property -> Property Units -> Payment Plan Template

SALES
  Lead                  status, source, follow-ups, WhatsApp, click-to-call
    v  Create > Opportunity          (ERPNext native)
  Opportunity           property mandatory, requirement captured
    v  Create > Property Booking
  Property Booking      agreement value, payment plan template

ON SUBMIT
  unit -> Booked | Payment Plan generated | portal user | Drive folder
  | commission entry | opportunity -> Converted

MONEY
  Payment Plan row due -> Sales Invoice -> reminders -> Payment Entry -> receipt

HANDOVER
  Property Agreement -> Property Allocation -> maintenance billing starts
```

There is a second, shorter path for walk-ins: open the unit, **Create >
Property Booking**. No Opportunity needed for a customer who points at a plot
and pays.

## Follow-ups

`Property Follow Up` is a Dynamic Link across Lead, Opportunity, Property
Booking, Property Unit and Customer. The call trail therefore survives
conversion instead of dying with the lead, which is what happened when
follow-ups were CRM Task rows under CRM Lead.

Closing a follow-up with a next date writes that date back onto the Lead, which
is what the daily reminder job reads.

## Lead status

The sales team's 40 statuses live in `custom_lead_status`, unchanged from the
CRM list they use today. Native `Lead.status` is derived from it (read-only on
the form) so ERPNext's own conversion logic and every stock report still work:

| Sales status | System status |
|---|---|
| Booked, converted | Converted |
| Interested, Under Negotiation, Site Visit * , CP Visit | Interested |
| Followup, Call in Future, Just Enquired, Whatsapp, CP Leads, Channel Partner, Farm-Stay Enquiry | Replied |
| DND, Junk, Duplicate, Not Interested, Number Invalid, Already Purchased, Dropped the Plan, Lost to * , Location Mismatch, Checking Other Developers, Different Requirement, Looking for * , vendor, Developer, Agent, Job Enquiry | Do Not Contact |
| everything else | Open |

The 60 sources are also carried over verbatim, and each one now exists as a
native `Lead Source` record, so `Lead.source` stays populated for stock CRM
reports.

Row-level visibility follows the same rule the team has now: Administrator and
Super Admin see everything, a supervisor sees their team's leads (via
`Employee.reports_to`), everyone else sees what they own or are assigned. Dead
statuses are filtered out of the working queue.

## Cutting over the JD site

The old setup relabelled ERPNext — Item was "Plot", Sales Order was "Booking
Form" — and ran the CRM in Frappe CRM. Nothing is deleted during cutover:

```bash
# 1. See what is still live and what replaced it
bench --site <site> execute property_core.property_core.migration.jd_legacy.report

# 2. Drop the Translation rows that renamed the doctypes (dry run first)
bench --site <site> execute property_core.property_core.migration.jd_legacy.revert_doctype_labels
bench --site <site> execute property_core.property_core.migration.jd_legacy.revert_doctype_labels \
    --kwargs "{'apply': True}"

# 3. Stand down the superseded site scripts (dry run first)
bench --site <site> execute property_core.property_core.migration.jd_legacy.disable_legacy_scripts
bench --site <site> execute property_core.property_core.migration.jd_legacy.disable_legacy_scripts \
    --kwargs "{'apply': True}"

# if something turns out to be missing in production
bench --site <site> execute property_core.property_core.migration.jd_legacy.restore_legacy_scripts \
    --kwargs "{'apply': True}"
```

Existing CRM Lead records stay where they are. New leads start in ERPNext
`Lead`.

Three things have **no** replacement yet and are deliberately left running —
`report` lists them: Drive permission sync on Project save, phone-number
normalisation on save, and CRM Lead delete housekeeping.

## Settings

Click-to-call needs Property Core Settings > Telephony: enable it, then the
Exotel account SID, caller ID, API key and token. They are read from the
settings record, never from code.
