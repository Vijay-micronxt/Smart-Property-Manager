# Smart Property Manager — Customer Portal API

Backend for any customer-facing portal (web, mobile, or a Frappe Web Page) built
on this app. Every endpoint is a whitelisted Python method inside the app — no
Server Scripts, so the whole surface is versioned with the code.

**Last verified:** 4 August 2026 — every response below was captured live from
`review.site` as the portal user `portal.test@example.com`.

---

## 1. Connection

| | |
|---|---|
| **Base path** | `/api/method/property_core.api.portal.<module>.<function>` |
| **Auth** | `Authorization: token <api_key>:<api_secret>` — or a normal session cookie |
| **Method** | `POST` (GET also works for the read-only ones) |
| **Content-Type** | `application/x-www-form-urlencoded` (JSON bodies work too) |
| **Guest access** | None. Unauthenticated calls get HTTP 403 |

```
Authorization: token d97e0c3b2804bc0:3371737aaf766b0
Content-Type: application/x-www-form-urlencoded
```

### Getting a token

```bash
curl -X POST "$BASE/api/method/property_core.api.auth.login" \
  -d "usr=portal.test@example.com" -d "pwd=<password>"
```

```json
{"message": {"status": "ok", "message": null,
 "data": {"user": "portal.test@example.com", "full_name": "Portal Test Customer",
          "api_key": "d97e0c3b2804bc0", "api_secret": "3371737aaf766b0"}}}
```

Auth endpoints (`property_core.api.auth.*`): `login`, `get_token`, `logout`,
`get_logged_in_user`, `change_password`, `forgot_password` (OTP),
`reset_password`.

### The token identifies the customer

No endpoint takes a `customer` parameter. The session user resolves to exactly
one Customer, and every query is scoped to it:

1. `Portal User` child row on Customer where `user = session.user`
2. Fallback — `Contact.email_id = session.user` → `Dynamic Link` → Customer

Neither match →
`No customer account is linked to your login. Please contact our team.`

Anything the client names — a unit, booking, invoice, issue — is checked against
that customer before it is read. A unit belongs to the customer if they own it
(`Property Unit.customer`), have a live booking on it, or hold an allocation.

### Response envelope

Every endpoint answers with the same shape:

```json
{"message": {"status": "ok", "message": null, "data": { ... }}}
```

`message` (the inner one) carries a human-readable line on write endpoints;
`data` is the payload documented below. Errors use Frappe's standard format —
see §9.

---

## 2. Endpoint Summary

| Module | Function | Params | Purpose |
|---|---|---|---|
| `meta` | `settings` | — | labels, colours, currency, feature flags |
| `profile` | `me` | — | who is logged in |
| `profile` | `update_contact` | `mobile_no`, `phone`, `first_name`, `last_name` | edit own contact |
| `dashboard` | `summary` | `recent_limit` | one call for a home screen |
| `properties` | `my_units` | — | units the customer holds |
| `properties` | `unit` | `property_unit` | one unit in full |
| `properties` | `projects` | — | properties/projects they are in |
| `properties` | `site_map` | `property` | layout geometry for the map |
| `properties` | `available_units` | `property`, `unit_type`, `limit` | bookable inventory |
| `bookings` | `list_bookings` | `status`, `limit` | bookings + payment plan |
| `bookings` | `booking_details` | `booking` | one booking in full |
| `bookings` | `book_unit` | `property_unit`, `note` | **request a booking** |
| `billing` | `charges` | `property_unit`, `charge_type`, `status`, `limit` | **all charges, one feed** |
| `billing` | `maintenance_charges` | `property_unit`, `status`, `limit` | recurring maintenance |
| `billing` | `utility_bills` | `property_unit`, `status`, `limit` | metered utilities |
| `billing` | `rent_history` | `property_unit`, `limit` | rent billing runs |
| `billing` | `outstanding_dues` | — | unpaid invoices + totals |
| `billing` | `payments` | `limit` | payments received |
| `billing` | `invoice` | `invoice` | one invoice + items + payments |
| `billing` | `payment_schedule` | `booking` | milestone plan |
| `maintenance` | `work_history` | `property_unit`, `status`, `limit` | **what work was done** |
| `maintenance` | `schedule` | `property_unit` | what is due next |
| `maintenance` | `inspections` | `property_unit`, `limit` | inspection results |
| `support` | `issues` | `property_unit`, `status`, `limit` | tickets + work orders |
| `support` | `issue` | `issue` | one ticket + conversation |
| `support` | `raise_issue` | `subject`, `description`, `property_unit`, `priority` | **open a ticket** |
| `support` | `add_comment` | `issue`, `message` | **reply on a ticket** |
| `documents` | `list_documents` | `property_unit`, `limit` | document index |

Write endpoints are bold. Everything else is read-only.

---

## 3. Bootstrap — `meta.settings`

Call once at startup so the client hardcodes no label, colour or currency.

```bash
curl -X POST "$BASE/api/method/property_core.api.portal.meta.settings" \
  -H "Authorization: token $TOKEN"
```

```json
{
 "api_version": "1.0.0",
 "customer": "Portal Test Customer",
 "currency": "INR",
 "company": "TP Private Limited",
 "status_colors": {"Available": "#22c55e", "Reserved": "#eab308", "Booked": "#f97316",
                   "Allocated": "#ef4444", "Leased": "#8b5cf6", "Maintenance Blocked": "#64748b"},
 "unit_statuses": ["Available", "Reserved", "Booked", "Allocated", "Leased", "Maintenance Blocked"],
 "unit_types": ["Plot", "Flat", "Villa", "Office", "Warehouse", "Shop"],
 "booking_statuses": ["Draft", "Reserved", "Confirmed", "Cancelled"],
 "issue_statuses": ["Open", "Replied", "Paused", "Resolved", "Closed"],
 "charge_types": ["Booking Milestone", "Maintenance", "Utility", "Rent", "Other"],
 "charge_statuses": ["Paid", "Overdue", "Due Soon", "Upcoming"],
 "features": {"booking": true, "issues": true, "maintenance": true,
              "utilities": true, "inspections": true, "site_map": true}
}
```

`api_version` changes whenever a payload shape changes in a way a client must
notice. Adding a field never bumps it.

---

## 4. Home screen — `dashboard.summary`

One call: headline numbers plus the few rows a landing page shows. Every section
has a dedicated endpoint that returns the full list when the customer opens
that tab.

```json
{
 "customer": {"name": "Portal Test Customer", "customer_name": "Portal Test Customer"},
 "totals": {
   "units": 1, "bookings": 1,
   "outstanding": 9505260.0, "overdue": 480260.0, "paid": 2000.0,
   "open_issues": 1, "open_work_orders": 0
 },
 "by_charge_type": {
   "Booking Milestone": {"count": 4, "amount": 9500000.0, "outstanding": 9500000.0},
   "Maintenance":       {"count": 3, "amount": 6000.0,    "outstanding": 4000.0},
   "Utility":           {"count": 1, "amount": 1260.0,    "outstanding": 1260.0}
 },
 "next_due": {
   "charge_type": "Maintenance", "reference_doctype": "Sales Invoice",
   "reference": "ACC-SINV-2026-00009", "property_unit": "UNIT-0004",
   "period": "2026-06", "amount": 2000.0, "outstanding": 2000.0,
   "due_date": "2026-06-23", "invoice": "ACC-SINV-2026-00009", "status": "Overdue"
 },
 "recent_bookings": [...], "recent_payments": [...],
 "recent_work_orders": [...], "open_issues": [...]
}
```

---

## 5. Money

### 5.1 `billing.charges` — every charge in one feed

The endpoint a "Payments" tab needs. It merges four sources and tags each row
with `charge_type`, so the client renders one table without knowing which
doctype a row came from.

| `charge_type` | Source | Notes |
|---|---|---|
| `Booking Milestone` | Payment Plan | instalments on a booking |
| `Maintenance` | Sales Invoice with `maintenance_period` | raised by the daily maintenance job |
| `Rent` | Sales Invoice listed in a Rent Invoice Log | recurring rent billing |
| `Utility` | Utility Bill not yet invoiced | invoiced ones arrive as `Other`/`Maintenance` |
| `Other` | any other submitted Sales Invoice | |

```json
{
 "charges": [
  {"charge_type": "Booking Milestone", "reference_doctype": "Payment Plan",
   "reference": "PP-0010", "property_unit": "UNIT-0004", "booking": "BKG-0005",
   "description": "On Agreement", "period": null, "amount": 1425000.0,
   "outstanding": 1425000.0, "due_date": "2026-08-23", "invoice": null,
   "status": "Upcoming"},
  {"charge_type": "Utility", "reference_doctype": "Utility Bill",
   "reference": "UBIL-0001", "property_unit": "UNIT-0004", "booking": null,
   "description": "Utility usage 28.0 units", "period": "2026-06-30",
   "amount": 1260.0, "outstanding": 1260.0, "due_date": "2026-07-30",
   "invoice": null, "status": "Overdue"}
 ],
 "totals": {"total": 9507260.0, "outstanding": 9505260.0, "overdue": 480260.0, "paid": 2000.0},
 "by_type": {"Booking Milestone": {...}, "Maintenance": {...}, "Utility": {...}},
 "count": 8
}
```

Filters: `charge_type`, `status`, `property_unit`, `limit` (default 200).

**Status rule** — shared by every charge type: `outstanding <= 0` → `Paid`;
else past due date → `Overdue`; else due within 7 days → `Due Soon`; else
`Upcoming`.

### 5.2 `billing.maintenance_charges`

The maintenance equivalent of JD's `customer_portal_maintenance`. Reads the
Sales Invoices the daily job stamps with `maintenance_period`.

```json
{
 "charges": [
  {"name": "ACC-SINV-2026-00010", "posting_date": "2026-07-23", "due_date": "2026-07-23",
   "grand_total": 2000.0, "outstanding_amount": 2000.0, "status": "Overdue",
   "currency": "INR", "remarks": "No Remarks", "property_unit": "UNIT-0004",
   "maintenance_period": "2026-07", "period": "2026-07", "unit_number": "E-401"}
 ],
 "total_due": 4000.0, "total_billed": 6000.0, "count": 3
}
```

### 5.3 Other money endpoints

- `billing.outstanding_dues` — unpaid submitted invoices, oldest first, plus
  `total_outstanding`, `total_overdue`, `invoice_count`.
- `billing.payments` — Payment Entries with `allocated_to` (which invoices each
  settled) and `total_paid`.
- `billing.invoice(invoice)` — one invoice with `items[]` and `payments[]`.
- `billing.payment_schedule(booking)` — milestone plan with per-row status and
  `total_amount` / `total_unpaid`.
- `billing.utility_bills` — bills with the `meter` they were read from.
- `billing.rent_history` — Rent Invoice Log rows with `invoice_details`.

**No payment gateway endpoint is exposed here.** Razorpay/Mswipe/Paytm methods
exist in the app for desk and webhook flows; a portal "pay now" call is
deliberately not part of this API yet.

---

## 6. Maintenance — what was done, what is next

### 6.1 `maintenance.work_history`

The "kya kaam hua" feed: every Work Order on the customer's units, with the
complaint it came from.

```json
{
 "work_orders": [
  {"name": "WO-0003", "issue": "ISS-2026-00002", "property_unit": "UNIT-0004",
   "status": "Completed", "description": "Fix bathroom sink leak",
   "scheduled_date": "2026-07-23", "completed_date": "2026-07-23",
   "actual_cost": 800.0, "notes": null, "unit_number": "E-401",
   "issue_details": {"subject": "Water leakage in bathroom", "status": "Resolved",
                     "opening_date": "2026-07-23"}}
 ],
 "summary": {"completed": 1, "open": 0, "total_cost": 800.0,
             "by_status": {"Completed": 1}},
 "total": 1
}
```

### 6.2 `maintenance.schedule`

What the unit's Maintenance Plan Template will service and bill next. Periods
already invoiced come back with `billed: 1`.

```json
{
 "schedule": [
  {"property_unit": "UNIT-0004", "unit_number": "E-401",
   "template": "Standard Monthly - Emerald Heights", "kind": "Scheduled",
   "description": null, "month_no": 1, "amount": 2000.0,
   "due_date": "2026-05-23", "period": "2026-05", "billed": 1, "paused": 0},
  {"property_unit": "UNIT-0004", "unit_number": "E-401",
   "template": "Standard Monthly - Emerald Heights", "kind": "Scheduled",
   "description": null, "month_no": 2, "amount": 2000.0,
   "due_date": "2026-06-23", "period": "2026-06", "billed": 1, "paused": 0}
 ],
 "total": 3
}
```

`due_date` is derived from the unit's `maintenance_start_date` plus `month_no`
when the template row carries no fixed date. `kind: "Recurring"` rows describe
the repeat cycle and carry no date.

### 6.3 `maintenance.inspections`

Inspection Checklists with their line items (`item_name`, `category`,
`condition`, `remarks`).

---

## 7. Property, map and booking

### 7.1 `properties.my_units` / `properties.unit`

`unit(property_unit)` returns `unit`, `property`, `project` (ERPNext Project with
`percent_complete`), `amenities`, `property_documents`, `allocation`,
`agreement` and `booking` in one payload.

### 7.2 `properties.site_map`

Layout geometry for the map view — the same engine data the desk Layout Editor
writes.

```json
{
 "properties": [
  {"property": {"name": "Emerald Heights", "property_name": "Emerald Heights",
                "project": "PROJ-0001",
                "layout_image": "/private/files/village-view-from_1385-477.avif",
                "world_width": 3000, "world_height": 2000,
                "annotations": [{"type": "emoji", "x": 955.93, "y": 1024.79,
                                 "size": 75, "char": "🚗"}]},
   "units": [
     {"name": "UNIT-0001", "unit_number": "E-301", "unit_type": "Flat",
      "availability_status": "Allocated", "area": 1350.0, "base_price": 8500000.0,
      "layout_shape": "Circle", "layout_x": 344.66, "layout_y": 1035.73,
      "layout_w": 509.68, "layout_h": 509.68, "layout_rotation": 0.0,
      "layout_points": "", "mine": 0, "bookable": 0}
   ]}
 ],
 "status_colors": {...}
}
```

Other customers' identities are never exposed — the `customer` field is stripped
and replaced by `mine`.

### 7.3 `bookings.book_unit` — request a booking

Creates a **draft** Property Booking for staff to verify and submit, and a
high-priority ToDo for every enabled Property Manager. Price comes from the
unit; the client cannot set it.

```bash
curl -X POST "$BASE/api/method/property_core.api.portal.bookings.book_unit" \
  -H "Authorization: token $TOKEN" \
  -d "property_unit=UNIT-0005" -d "note=Interested, please hold."
```

```json
{"status": "ok",
 "message": "Booking request received. Our team will confirm shortly.",
 "data": {"booking": "BKG-0006", "unit": "E-402", "property_unit": "UNIT-0005",
          "status": "pending_confirmation"}}
```

Validation order: unit exists → `availability_status == "Available"` → no other
live booking on it. `book_unit` **mutates state** — the unit flips to `Booked`.
To re-test, cancel and delete the booking and set the unit back to `Available`.

---

## 8. Support

- `support.issues` — tickets with the `work_orders[]` raised against each, plus
  `open_count`. `status=Open` expands to Open/Replied/Paused.
- `support.issue(issue)` — one ticket with `work_orders[]` and `comments[]`.
- `support.raise_issue(subject, description, property_unit, priority)` — opens a
  ticket; a unit, if given, must be the customer's own.
- `support.add_comment(issue, message)` — customer reply on their own ticket.

```json
{"status": "ok", "message": "Ticket raised. Our team will get back to you.",
 "data": {"issue": "ISS-2026-00003", "status": "Open"}}
```

`documents.list_documents` returns a flat index of what the estate already
attaches — Property Document rows, the agreement PDF, and File attachments on
the customer's bookings, agreements, allocations and invoices:

```json
{"documents": [
   {"source": "Agreement", "reference_doctype": "Property Agreement",
    "reference": "AGMT-0001", "property_unit": "UNIT-0004",
    "title": "Sale Agreement - AGMT-0001", "document_type": "Sale Agreement",
    "file_url": "/files/sale-agreement-e401.pdf", "expiry_date": "2028-07-04",
    "modified": "2026-08-04 16:17:21"}],
 "by_source": {"Agreement": 1}, "total": 1}
```

It hands back links, not bytes — private files still go through Frappe's own
file permission check.

---

## 9. Errors

Frappe returns **HTTP 417** for `frappe.throw()`, **403** for unauthenticated
calls.

```json
{
 "exception": "frappe.exceptions.ValidationError: Selected unit does not belong to your account",
 "exc_type": "ValidationError",
 "_server_messages": "[\"{\\\"message\\\": \\\"Selected unit does not belong to your account\\\"}\"]"
}
```

```js
function portalError(body) {
  try {
    if (body._server_messages) return JSON.parse(JSON.parse(body._server_messages)[0]).message;
    if (body.exception) return body.exception.split(':').pop().trim();
  } catch (e) {}
  return 'Something went wrong';
}
```

| Code | Meaning |
|---|---|
| 200 | success — read `message.data` |
| 403 | not authenticated |
| 417 | validation error — read `_server_messages` |
| 500 | server exception |

Guard messages worth handling explicitly:

| Message | Cause |
|---|---|
| `No customer account is linked to your login. Please contact our team.` | user has no Portal User row and no Contact match |
| `Selected unit does not belong to your account` | unit not owned/booked/allocated by this customer |
| `Sales Invoice X does not belong to your account` | invoice belongs to another customer |
| `Unit E-402 is not available` | someone booked it first |

---

## 10. Adding fields later

Payload field lists live in one place — `property_core/api/portal/fields.py` —
not inside the queries. Three ways to extend, cheapest first:

1. **Add a custom field on the site.** Any `custom_*` field on Property,
   Property Unit, Property Booking, Property Allocation, Property Agreement,
   Issue or Work Order is included automatically. No code change.
2. **Add it to `REGISTRY`** in `fields.py` — one line — for a standard field or
   a doctype not in the auto-custom set.
3. **Hook it from another app** without touching this one:

   ```python
   # in your app's hooks.py
   portal_extra_fields = {"Property Unit": ["custom_khata_number"]}
   ```

Fields that do not exist on a site are dropped rather than raising, so a renamed
or removed field degrades to a missing key instead of a 500. Secrets
(`api_secret`, gateway keys) are blocklisted and can never be exposed this way.

**Project link.** `Property.project` is an optional link to an ERPNext Project;
it flows down to Property Unit, Booking, Allocation and Agreement as a read-only
fetched field and is returned by `properties.unit`, `properties.projects`,
`bookings.*` and `site_map`. Set it on the Property and everything below inherits
it on next save. Bookings created before the field existed resolve it from their
unit at read time.

---

## 11. Legacy endpoints

`property_core.property_core.api.customer_portal.*` (11 methods:
`customer_portal_get`, `get_maintenance_requests`, `get_utility_bills`,
`get_outstanding_dues`, `get_payment_history`, `get_unit_details`,
`get_inspection_reports`, `get_rent_history`, `site_map`, `book_unit`,
`raise_issue`) still work unchanged — they return raw dicts with no envelope and
are what the bundled `/customer-portal` page calls. New clients should use
`property_core.api.portal.*`.

---

## 12. Test data used above

`review.site`, customer `Portal Test Customer`, login `portal.test@example.com`.

| | |
|---|---|
| Property | `Emerald Heights` → Project `PROJ-0001` |
| Unit | `UNIT-0004` (E-401, Booked), `UNIT-0005` (E-402, Available) |
| Booking | `BKG-0005` confirmed, 4 milestones totalling ₹95,00,000 |
| Maintenance | `ACC-SINV-2026-00008/9/10` — periods 2026-05/06/07 @ ₹2,000 |
| Payment | `ACC-PAY-2026-00001` — ₹2,000 against 2026-05 |
| Utility | `UBIL-0001` — 28 m³ @ ₹45 |
| Work | `WO-0003` completed sink-leak repair, ₹800 |
| Inspection | `INS-0001` with 2 checklist rows |
| Agreement | `AGMT-0001` with attached PDF |
