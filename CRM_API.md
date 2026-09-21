# CRM API — enquiry to booking

Staff-facing HTTP API for the sales app: leads, follow-ups, opportunities,
customers, inventory, bookings, and the project roll-up everything is read
through.

This is a separate surface from the customer portal API
(`CUSTOMER_PORTAL_API.md`). That one is for buyers; this one is for the sales
floor.

---

## 1. Base URL and envelope

Every endpoint is a Frappe whitelisted method:

```
https://<site>/api/method/property_core.api.crm.<module>.<function>
```

Frappe wraps its own reply in `message`, and the API's envelope is inside it:

```json
{
  "message": {
    "status": "ok",
    "message": "Lead CRM-LEAD-2026-00010 created",
    "data": { "...": "..." }
  }
}
```

So the payload the app wants is always `response.message.data`.

Errors come back as an HTTP 4xx/5xx with Frappe's own body:

```json
{
  "exception": "frappe.exceptions.ValidationError: Pick a property — an opportunity cannot be worked without one.",
  "exc_type": "ValidationError",
  "_server_messages": "[{\"message\": \"...\"}]"
}
```

Read `exc_type` for the kind of failure and `_server_messages[0].message` for
the sentence to show the user. The ones worth handling by name:

| `exc_type` | Meaning |
|---|---|
| `AuthenticationError` | not logged in / bad token |
| `PermissionError` | logged in, but this record or doctype is not theirs |
| `ValidationError` | the request was refused for a business reason |
| `DoesNotExistError` | no such record — or one the caller may not see |
| `MandatoryError` | a required field was not sent |

GET is fine for every read; use POST with `Content-Type: application/json` for
anything that writes.

---

## 2. Login

`frappe.auth.get_logged_user` is **not** callable on the live site — it answers
*"Function frappe.auth.get_logged_user is not whitelisted"*. Use
`session.whoami` instead; it returns the user, their roles, what they are
allowed to see and every default the app needs, in one request.

### `session.login` (guest)

```http
POST /api/method/property_core.api.crm.session.login
Content-Type: application/json

{"usr": "sales@jdfarmlands.com", "pwd": "••••••"}
```

```json
{"message": {"status": "ok", "data": {
  "user": "sales@jdfarmlands.com",
  "full_name": "Sales Desk",
  "api_key": "0b1c…",
  "api_secret": "9fd3…",
  "scope": "team",
  "roles": ["Property Sales Manager", "Employee", "All"],
  "team": ["hema@jdfarmlands.com", "swarna@jdframlands.com"],
  "permissions": {"Lead": {"read": true, "write": true, "create": true, "delete": false}},
  "defaults": {"company": "JD Farmlands", "currency": "INR", "date_format": "dd-mm-yyyy"}
}}}
```

Send the token on every later call:

```
Authorization: token <api_key>:<api_secret>
```

A normal browser session cookie works too — nothing requires the token.

| Endpoint | Method | What it does |
|---|---|---|
| `session.login` | POST | authenticate, returns token + profile |
| `session.whoami` (alias `session.me`) | GET | the same profile for the current login |
| `session.refresh_token` | POST | new `api_key`/`api_secret` |
| `session.logout` | POST | end the session |

---

## 3. Who sees what

Three tiers, decided by role — the app does not have to filter anything, every
listing already comes back scoped:

| `scope` | Role | Sees |
|---|---|---|
| `all` | `Property Manager` (or System Manager / Administrator) | the whole company |
| `team` | `Property Sales Manager` | their own records **and everyone below them in the Employee reporting tree**, at any depth |
| `own` | `Property Sales Executive` (or `Sales User`) | only what they own or were assigned |

The tree is `Employee.reports_to`. A user with no Employee record is treated as
an executive.

Applies to **Lead, Opportunity, Property Booking, Property Follow Up**.
Inventory (Project, Property, Property Unit) is visible to the whole floor —
you cannot sell what you cannot see.

Ownership means any of: `lead_owner` / `opportunity_owner` / document owner /
`custom_follow_up_owner` / an open assignment (ToDo) / the `sales_person` on a
booking.

Dead lead statuses (Junk, Not Interested, Number Invalid, …) are hidden from
everyone except admins, so a sales list stays the live pipeline.

---

## 4. Meta — one call at app start

| Endpoint | Returns |
|---|---|
| `meta.options` | every dropdown: lead statuses and sources, unit types, facings, opportunity statuses/stages, follow-up types and outcomes, booking statuses, payment plan templates, property types, companies, currency |
| `meta.field_options?doctype=&fieldname=` | one field's Select options |

Never hardcode a status list — JD edits theirs.

---

## 5. Leads

| Endpoint | Method | Notes |
|---|---|---|
| `leads.get_leads` | GET | paged list |
| `leads.get_lead?name=` | GET | lead + follow-ups + opportunities + bookings + customer + activity |
| `leads.create_lead` | POST | `data` object of fields |
| `leads.update_lead` | POST | `name` + `data` |
| `leads.set_status` | POST | `name`, `status`, optional `notes` |
| `leads.assign_lead` | POST | `name`, `user` — moves the follow-up owner **and** the ToDo |
| `leads.transfer_ownership` | POST | `name`, `user` — hands the lead over outright |
| `leads.convert_to_opportunity` | POST | see below |
| `leads.create_customer` | POST | `name` — Lead → Customer, address carried over |
| `leads.find_duplicates` | GET | `mobile_no` — same number already in the system |
| `leads.pipeline` | GET | counts per status, for the funnel chart |

`get_leads` filters: `search` (name/mobile/email/company), `status` (string or
JSON array), `source`, `owner`, `mine=1`, `property`, `project`, `unit_type`,
`from_date`, `to_date`, `order_by`, `page`, `page_size` (max 100), plus a raw
`filters` array if the screen needs something unusual.

Every list answers the same shape:

```json
{"rows": [...], "page": 1, "page_size": 20, "total": 143, "has_more": true}
```

### Lead → Opportunity

```http
POST /api/method/property_core.api.crm.leads.convert_to_opportunity
{"name": "CRM-LEAD-2026-00010", "property_unit": "UNIT-0051"}
```

* Sending only `property_unit` is enough — the property is taken off the unit.
* `opportunity_amount` defaults to the unit's base price.
* Calling it twice does not make a second opportunity: the existing one comes
  back with `"already_existed": true`.
* Optional: `property`, `opportunity_amount`, `expected_closing`,
  `next_follow_up_on`, `notes`.

---

## 6. Follow-ups

The activity trail that survives conversion — the same history follows a
person from Lead to Opportunity to Booking.

| Endpoint | Method | Notes |
|---|---|---|
| `follow_ups.get_follow_ups` | GET | filters: `reference_doctype`, `reference_name`, `status`, `assigned_to`, `mine=1`, `follow_up_type`, `from_date`, `to_date` |
| `follow_ups.get_follow_up?name=` | GET | one record |
| `follow_ups.create_follow_up` | POST | schedule the next touch |
| `follow_ups.log_follow_up` | POST | record a call that already happened, and optionally book the next |
| `follow_ups.complete_follow_up` | POST | `name`, `outcome`, `notes`, `next_follow_up_on`, `next_action` |
| `follow_ups.reschedule` | POST | `name`, `scheduled_on` |
| `follow_ups.cancel_follow_up` | POST | `name`, `reason` |
| `follow_ups.my_agenda` | GET | `overdue` / `today` / `upcoming` buckets with counts — the home screen |

`create_follow_up` needs only `reference_doctype` + `reference_name`; party
name, phone number, property and unit are pulled off the reference.

A `next_follow_up_on` on completion raises the next follow-up automatically —
that chaining is what stops a lead going cold.

---

## 7. Opportunities

| Endpoint | Method | Notes |
|---|---|---|
| `opportunities.get_opportunities` | GET | filters: `search`, `status`, `property`, `project`, `property_unit`, `owner`, `mine=1`, `from_date`, `to_date` |
| `opportunities.get_opportunity?name=` | GET | opportunity + unit summary + follow-ups + bookings + customer + `can_book` |
| `opportunities.create_opportunity` | POST | direct opportunity (walk-in) |
| `opportunities.update_opportunity` | POST | `name` + `data` |
| `opportunities.set_property` | POST | tag property and/or unit |
| `opportunities.set_status` | POST | `name`, `status`, `reason` (for Lost) |
| `opportunities.convert_to_booking` | POST | see below |
| `opportunities.funnel` | GET | count and value per status |

### Property and unit tagging

The rule the desk form follows, and the API with it:

* Send **only `property_unit`** → the property is filled from the unit.
* Send **only `property`** → the unit stays empty; list the sellable units with
  `inventory.available_units?property=…`.
* Send a unit that belongs to a **different** property → refused
  (`ValidationError`), never silently retagged.

```http
POST /api/method/property_core.api.crm.opportunities.set_property
{"name": "CRM-OPP-2026-00009", "property_unit": "UNIT-0051"}
```

```json
{"data": {
  "custom_property": "CRM Smoke Property",
  "custom_property_unit": "UNIT-0051",
  "custom_project": "PROJ-0003",
  "opportunity_amount": 2600000.0,
  "unit": {"unit_number": "S162908-1", "base_price": 2600000.0, "availability_status": "Available", "project": "PROJ-0003"}
}}
```

`custom_project` is stamped from the property automatically — it is what every
project report reads.

### Opportunity → Booking

```http
POST /api/method/property_core.api.crm.opportunities.convert_to_booking
{"name": "CRM-OPP-2026-00009", "booking_amount": 100000}
```

Everything else is derived:

* unit and property from the opportunity,
* agreement value (`total_price`) from the unit's base price,
* **customer from the lead — created if the lead was never converted**, since a
  booking cannot exist without one,
* `opportunity` and `lead` links back, so the funnel stays walkable.

Optional: `booking_date`, `total_price`, `payment_plan_template`,
`sales_person`, `property_unit` (to override), `notes`, `submit=1`.

The booking is created as a **draft**. Confirming it is a separate call
(`bookings.submit_booking`) and a separate permission.

---

## 8. Customers

| Endpoint | Method | Notes |
|---|---|---|
| `customers.get_customers` | GET | `search`, `filters`, paging |
| `customers.get_customer?name=` | GET | customer + bookings + units + outstanding + follow-ups |
| `customers.create_customer` | POST | `data` |
| `customers.create_from_lead` | POST | `lead` — idempotent |

---

## 9. Inventory

Read-only for sales: the project, its properties and their units are set up
before anybody sells.

| Endpoint | Method | Notes |
|---|---|---|
| `inventory.get_properties` | GET | `project`, `search`, `status`, `property_type`; each row carries a `units` count breakdown |
| `inventory.get_property?name=` | GET | property + unit stats |
| `inventory.get_units` | GET | `property`, `project`, `availability`, `unit_type`, `facing`, `min_price`, `max_price`, `min_area`, `max_area`, `search` |
| `inventory.available_units` | GET | the same, pre-filtered to Available + Reserved |
| `inventory.get_unit?name=` | GET | unit + open booking + live opportunities on it |
| `inventory.resolve_unit?property_unit=` | GET | **the auto-fill call**: property, project, price, plan, availability |
| `inventory.availability` | GET | `project` or `property` — counts by status, inventory value |

The map on Property and Property Unit takes a place name, a pasted coordinate
pair, or a Google Maps link (the short `maps.app.goo.gl` kind included — the
server follows the redirect). `latitude`, `longitude` and `map_link` come back
on every unit and property payload, so the app never has to open a map to know
where something is.

---

## 10. Bookings

| Endpoint | Method | Notes |
|---|---|---|
| `bookings.get_bookings` | GET | `customer`, `property`, `project`, `property_unit`, `status`, `docstatus`, `mine=1`, `from_date`, `to_date` |
| `bookings.get_booking?name=` | GET | booking + unit + payment plan + collections + follow-ups |
| `bookings.create_booking` | POST | walk-in path, straight off a unit |
| `bookings.update_booking` | POST | drafts only |
| `bookings.submit_booking` | POST | **confirms the deal** |
| `bookings.cancel_booking` | POST | puts the unit back on the market |
| `bookings.payment_plan?booking=` | GET | milestones + what is billed/collected |

Submitting is the real step: the unit is reserved, the payment plan is
generated, the customer's portal login is provisioned and maintenance billing
starts. A `Property Sales Executive` may raise a booking but **not** confirm
it; `Property Sales Manager` and `Property Manager` may.

---

## 11. Projects — the roll-up everything is read through

JD runs the business per development, so this is the screen a manager opens.

| Endpoint | Method | Returns |
|---|---|---|
| `projects.get_projects` | GET | projects with a `summary` (properties, units, available, booked, inventory value, bookings, booked value) |
| `projects.get_project?name=` | GET | project + summary + its properties |
| `projects.overview?name=` | GET | **everything in one call**: `inventory`, `funnel`, `sales`, `money`, `operations`, `team` |
| `projects.project_inventory?name=` | GET | per-property unit breakdown |
| `projects.project_funnel?name=` | GET | leads by status, opportunities by status + value, open follow-ups |
| `projects.project_bookings?name=` | GET | paged bookings under the development |
| `projects.project_operations?name=` | GET | work orders and issues by status |
| `projects.project_activity?name=` | GET | the last things that happened, across doctypes |

`overview` accepts `from_date` / `to_date` for the funnel and sales sections.

Sections the caller has no permission for (invoices, work orders) are left out
of the payload rather than failing the request.

---

## 12. Dashboard and team

| Endpoint | Method | Returns |
|---|---|---|
| `dashboard.summary` | GET | `today` (overdue / today's follow-ups / untouched leads), `leads`, `opportunities`, `bookings`, `conversion` rates, `projects` — all scoped to the caller |
| `team.my_team` | GET | the people under this login, flat list and nested tree |
| `team.assignable_users` | GET | who this login may assign work to |
| `team.performance` | GET | per person: leads, opportunities, bookings, confirmed value, open follow-ups (`from_date` / `to_date`) |

---

## 13. The whole flow, end to end

```
1.  session.login                          -> token, scope, permissions
2.  meta.options                           -> dropdowns
3.  leads.create_lead                      -> CRM-LEAD-2026-00010
4.  follow_ups.create_follow_up            -> next call booked
5.  follow_ups.complete_follow_up          -> outcome logged, next one chained
6.  inventory.available_units?project=…    -> pick a unit
7.  leads.convert_to_opportunity           -> CRM-OPP-2026-00009 (property auto-filled)
8.  opportunities.set_property             -> change of mind, unit swapped
9.  opportunities.convert_to_booking       -> BKG-0046 draft (customer auto-created)
10. bookings.submit_booking                -> unit reserved, payment plan raised
11. projects.overview                      -> the development, updated
```

Every step above is covered by the automated suites, run against
`review.site`:

| suite | what it proves |
|---|---|
| `property_core/tests/crm_api_smoke.py` | the funnel end to end, 38 assertions |
| `property_core/tests/crm_api_coverage.py` | the remaining endpoints, 59 assertions |
| `property_core/tests/crm_data_verify.py` | what actually reached the database — address, contact, payment plan, unit status, portal login — 51 assertions |

---

## 14. Notes for the app

* **Paging**: `page` starts at 1, `page_size` max 100. Use `has_more`, not row
  counts.
* **Dates** are ISO strings; datetimes are `YYYY-MM-DD HH:MM:SS` in the site's
  timezone (`defaults.time_zone` from `whoami`).
* **Money** is plain numbers in the site currency (`defaults.currency`).
* **Writable fields** are whitelisted per endpoint; anything else in `data` is
  ignored rather than rejected, so sending a whole record back is safe.
* **Idempotency**: `convert_to_opportunity`, `convert_to_booking` and
  `create_from_lead` all return the existing record instead of creating a
  second one.
* **Opportunity has no `contact_date`** — ERPNext 15.90 dropped it. The next
  touch is `custom_next_follow_up_date`, which follow-ups keep in step.
* **Do not** call `frappe.client.*` or the generic `/api/resource/…` routes for
  this data — they bypass the envelope and, for anything the app writes,
  the derivation rules above.
