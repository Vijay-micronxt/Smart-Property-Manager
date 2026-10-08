# CRM API — enquiry to booking

Staff-facing HTTP API for the CRM app — everything JD does on the ERPNext desk,
over JSON: leads, follow-ups, opportunities, customers, bookings; projects,
tasks, properties, units, templates and charges; invoices and payments;
agreement and allocation; attachments and Drive; plot layout and maps;
complaints and site work; maintenance visits with photo proof; and the
dashboards over all of it. 164 endpoints.

**Building the app? Start with `CRM_APP_GUIDE.md`** — screen by screen: which
call, when, with what payload, where each dropdown and auto-filled value comes
from.

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

Every endpoint except `session.login` needs the token (or a session cookie).
Called without one, Frappe answers *"You are not permitted to access this
resource. Login to access — Function … is not whitelisted"*. That message means
**not logged in**, not that the endpoint is missing.

`frappe.auth.get_logged_user` works once logged in, but returns only the user
id. `session.whoami` returns the user, their roles, what they are allowed to
see and every default the app needs, in one request — use that.

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
| `meta.options` | every dropdown: lead statuses and sources, unit types, facings, opportunity statuses/stages, follow-up types and outcomes, booking statuses, payment plan templates, sales persons, property types, companies, currency |
| `meta.field_options?doctype=&fieldname=` | one field's choices — Select options, or the values of the master a Link field points at |

Never hardcode a status list — JD edits theirs.

### Dropdowns are masters JD edits

These are Link fields onto small DocTypes. A new value is a new record in the
desk (or `POST /api/resource/<master>`), it shows up in `meta.options` on the
next call, and it can be saved at once — no code change, no deploy.

| `meta.options` key | Master |
|---|---|
| `lead.statuses` | Property Lead Status |
| `lead.sources`, `opportunity.sources` | Lead Source (ERPNext's own) |
| `follow_up.types` | Property Follow Up Type |
| `follow_up.outcomes` | Property Follow Up Outcome |
| `unit.types`, `lead.unit_types` | Property Unit Type |
| `unit.facings`, `lead.facings` | Property Facing |
| `property.types` | Property Type |

The same mapping comes back in `meta.options.masters`, for a screen that
wants a "+ new" button. Adding to a master needs Property Manager.

* Each master has **Enabled** and **Sort Order**. A disabled value leaves the
  dropdowns; records that already carry it keep it.
* Each **Property Lead Status** also says which ERPNext status it maps to and
  whether it is **hidden from the sales team**. `lead.status_details` returns
  those rules (`status`, `erpnext_status`, `hide_from_sales`, `indicator`);
  `lead.dead_statuses` is the hidden ones.
* A value that is not in the master is refused with
  `exc_type: LinkValidationError` (a kind of `ValidationError`) and the
  message *"Could not find Lead Status: …"*.

Workflow fields stay fixed lists, because the server acts on their values:
unit `availability`, booking `statuses`, follow-up `statuses`, property
`statuses`, opportunity `statuses`.

New in the payload, nothing removed or renamed: `lead.status_details`,
`booking.sales_persons` (the site's Sales Person records, groups left out —
`bookings.*.sales_person` must be one of them), `masters`, and `defaults` —
what a new record starts with, keyed like the lists
(`{"unit.availability": "Available", "follow_up.types": "Call", "company": …}`),
read off each field's own default so the app never picks one itself.

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
before anybody sells. The two create calls are for whoever sets that up
(Property Manager); an executive gets `PermissionError`.

| Endpoint | Method | Notes |
|---|---|---|
| `inventory.get_properties` | GET | `project`, `search`, `status`, `property_type`; each row carries a `units` count breakdown |
| `inventory.get_property?name=` | GET | property + unit stats |
| `inventory.get_units` | GET | `property`, `project`, `availability`, `unit_type`, `facing`, `min_price`, `max_price`, `min_area`, `max_area`, `search` |
| `inventory.available_units` | GET | the same, pre-filtered to Available + Reserved |
| `inventory.get_unit?name=` | GET | unit + open booking + live opportunities on it |
| `inventory.resolve_unit?property_unit=` | GET | **the auto-fill call**: property, project, price, plan, availability |
| `inventory.availability` | GET | `project` or `property` — counts by status, inventory value |
| `inventory.create_property` | POST | `data`: `property_name`, `property_type` (a Property Type), `company` (defaults to the user's), `project`, `status`, `launch_date`, `address`, `payment_plan_template`, `latitude`, `longitude`, `map_link` |
| `inventory.create_unit` | POST | `data`: `property`, `unit_number`, `unit_type` (a Property Unit Type), `area`, `base_price`, `facing`, `floor`, `availability_status` (defaults to Available), `payment_plan_template`, `latitude`, `longitude`, `map_link`; project comes off the property |

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
| `bookings.cancel_booking` | POST | puts the unit back on the market, stops its billing (unbilled instalments cancelled, unpaid invoices withdrawn) and returns `collected`, `forfeit`, `refund`, `refund_status` |
| `bookings.refund` | POST | `name*`, `mode_of_payment*`, `amount` (default the refund worked out on cancel), `posting_date`, `reference_no`, `reference_date` → credit note + Payment Entry paying the customer back |
| `bookings.payment_plan?booking=` | GET | milestones + what is billed/collected |

Submitting is the real step: the unit is reserved, the payment plan is
generated (the **booking amount is its first instalment**, invoiced at once;
any advance already received is set off against it), the customer's portal
login is provisioned and maintenance billing starts. A `Property Sales Executive` may raise a booking but **not** confirm
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

## 12. Dashboards and team

All dashboards take the same filters the old JD `get_dashboard_data` script took:

| Arg | Values |
|---|---|
| `view_type` | `my` (own + assigned to me) · `team` (my reporting tree) · `organisation` (everything this login may see) |
| `team_member` | `team` only: `"a@x.com,b@y.com"` narrows to those people (a manager can only pick people under them) |
| `date_range` | `all` · `today` · `yesterday` · `week` · `month` · `custom` |
| `date_from` / `date_to` | `custom` only, `YYYY-MM-DD`, both inclusive |

Every response also carries `user_type` (`admin` / `supervisor` / `regular`),
`view_type` and `team_members` (`[{user_id, name}]`, for the team switcher).
A `regular` login asking for `team` or `organisation` gets empty numbers, not
an error. The permission engine sits under all of it, so a manager asking for
`organisation` still only sees their own tree.

| Endpoint | Method | Returns |
|---|---|---|
| `dashboard.lead_dashboard` | GET | **drop-in for `/api/method/get_dashboard_data`** — same keys (`total_leads`, `pending_leads`, `status_counts[{status,count}]`, `source_counts[{source,count}]`, `filters`, `team_members`, `user_type`, `view_type`) but read from ERPNext **Lead**, not Frappe CRM's `CRM Lead`. Extra arg `date_field`: `creation` (default) / `modified` / `custom_next_follow_up_date` |
| `dashboard.flow` | GET | **the whole business, lead to money**, one call — see below. Extra arg `project` |
| `dashboard.trend` | GET | month by month (`months`, default 6, max 24): `leads`, `opportunities`, `bookings`, `booked_value`, `collected`. Also `project` |
| `dashboard.summary` | GET | the home screen: today's follow-ups, untouched leads, funnel, conversion, top projects (`from_date` / `to_date`) |
| `team.my_team` | GET | the people under this login, flat list and nested tree |
| `team.assignable_users` | GET | who this login may assign work to |
| `team.performance` | GET | per person: leads, opportunities, bookings, confirmed value, open follow-ups (`from_date` / `to_date`) |

Frontend switch for the old dashboard — change only the URL:

```
before: /api/method/get_dashboard_data?view_type=my
after:  /api/method/property_core.api.crm.dashboard.lead_dashboard?view_type=my
        (payload now at message.data instead of message)
```

`dashboard.flow?view_type=organisation&date_range=month` (trimmed):

```json
{
  "user_type": "admin", "view_type": "organisation", "team_members": [...],
  "leads":         {"total": 55, "converted": 33, "open_now": 22, "without_follow_up": 20,
                    "by_status": [{"status": "Interested", "count": 22}], "by_source": [...]},
  "follow_ups":    {"open": 12, "overdue": 3, "today": 4, "upcoming": 5},
  "opportunities": {"total": 46, "open": 22, "won": 20, "lost": 4, "pipeline_value": 20900000.0, "by_status": [...]},
  "customers":     {"new": 98, "with_booking": 57},
  "bookings":      {"total": 62, "draft": 4, "confirmed": 58, "from_opportunity": 17, "from_lead": 17,
                    "walk_in": 41, "booked_value": 171400000.0, "booking_amount": 14605000.0, "by_status": [...]},
  "allocations":   {"active": 1, "draft": 0, "pending_allocation": 57},
  "money":         {"billed": 21735000.0, "collected": 2560000.0, "outstanding": 19175000.0,
                    "overdue": 25855000.0, "due_next_30_days": 32145000.0, "collected_in_period": 2560000.0,
                    "unbilled_milestones": 227, "fully_paid_bookings": 0},
  "inventory":     {"total_units": 105, "available": 40, "sold": 64, "available_value": 90500000.0, "by_status": [...]},
  "conversion":    {"lead_to_opportunity": 83.6, "opportunity_to_booking": 37.0, "lead_to_booking": 30.9, "collection_rate": 11.8},
  "stages": [{"stage": "Leads", "count": 55}, {"stage": "Opportunities", "count": 46}, {"stage": "Bookings", "count": 62},
             {"stage": "Confirmed", "count": 58}, {"stage": "Allocated", "count": 1}, {"stage": "Fully paid", "count": 0}]
}
```

Counts inside the period are "new in the period" (lead created, opportunity
opened, booking dated, payment received). Pipeline numbers — `open_now`,
follow-ups, `outstanding`, `overdue` — are as of now. Money covers the
confirmed bookings in view. Conversion only counts bookings that came through
the funnel; walk-ins are reported separately.

---

## 13. Projects and tasks

| Endpoint | Method | Does |
|---|---|---|
| `projects.create_project` | POST | `data: {project_name*, status, project_type, expected_start_date, expected_end_date, estimated_costing, priority, department, customer, notes, company}` (company defaults to the user's) |
| `projects.update_project` | POST | `name`, `data` — same fields |
| `tasks.get_tasks` | GET | `project`, `status` (one or JSON list), `mine=1`, `assigned_to`, `overdue=1`, `parent_task`, `search`, paging. Rows carry `assigned_to: [{user, full_name}]` |
| `tasks.get_task` | GET | task + `assigned_to` + `subtasks` + `comments` |
| `tasks.create_task` | POST | `data: {subject*, project, status, priority, type, exp_start_date, exp_end_date, expected_time, parent_task, is_group, is_milestone, description, department, issue}`, `assign_to` (user or JSON list) |
| `tasks.update_task` | POST | `name`, `data` |
| `tasks.set_status` | POST | `name`, `status` (Open / Working / Pending Review / Overdue / Completed / Cancelled), `note`. Completed sets progress 100 |
| `tasks.assign_task` | POST | `name`, `user` (or list), `note`, `keep_others=0` — default gives the task one owner, releasing earlier ones |
| `tasks.unassign_task` | POST | `name`, `user` |
| `tasks.delete_task` | POST | `name` |
| `tasks.options` | GET | `statuses`, `priorities`, `types` |

Assignment is the desk's own ToDo, so a task given out in the app shows in the
assignee's desk ToDo and bell, and the other way round. For assigning *any*
record (lead, booking, unit …) see `activity.assign`.

---

## 14. Setting up inventory — properties, units, templates, charges

Order JD sets a development up in: project → property → units → templates.

| Endpoint | Method | Does |
|---|---|---|
| `inventory.create_property` | POST | `data: {property_name*, property_type*, project, status, company, launch_date, total_area, address, payment_plan_template, latitude, longitude, map_link}` |
| `inventory.update_property` | POST | `name`, `data` — same fields, plus `amenities: [{amenity_name, amenity_type, description}]` and `property_documents: [{document_name, document_type, document_file, expiry_date, notes}]` (each **replaces** the whole table) |
| `inventory.create_unit` | POST | `data: {property*, unit_number*, unit_type*, area, facing, floor, base_price, payment_plan_template, maintenance_plan_template, maintenance_start_date, pause_maintenance, latitude, longitude, map_link}` |
| `inventory.bulk_create_units` | POST | `property*` and either `units: [{unit_number, ...}]` or `prefix` + `start` + `count` (e.g. `A-`, 1, 40 → A-1 … A-40). `defaults: {unit_type, area, base_price, facing, ...}` applies to all. Existing unit numbers are skipped, so re-running is safe. Max 500 per call. Returns `created`, `skipped` |
| `inventory.update_unit` | POST | `name`, `data` — any unit field except `availability_status` |
| `inventory.set_unit_status` | POST | `name`, `status` = `Available` / `Reserved` / `Maintenance Blocked`, `reason`. Booked / Allocated / Leased are only ever set by a booking or allocation; a unit with a live one cannot be made Available here |
| `templates.get_payment_templates` | GET | every Payment Plan Template with `milestones` and `used_by` |
| `templates.get_payment_template` | GET | `name` |
| `templates.save_payment_template` | POST | `template_name`, `milestones: [{milestone, percentage, offset_months}]` (percentages must total 100); pass `name` to replace an existing one |
| `templates.delete_payment_template` | POST | `name` |
| `templates.preview_payment_plan` | GET | `amount` and `template`, or just `property_unit` (uses its template and base price), `booking_date` → the schedule with dates and amounts — show the customer before booking |
| `templates.get_maintenance_templates` | GET | recurring-charge templates (`include_disabled=1` for all) |
| `templates.get_maintenance_template` | GET | `name` |
| `templates.save_maintenance_template` | POST | `template_name`, `schedule: [{month_no (≥1) or fixed_due_date, description, amount, item_code}]` for one-off charges (corpus, club fee …), `repeat_every_n_months` + `repeat_amount` + `repeat_item_code` for the monthly/quarterly charge, `disabled`; `name` to replace |
| `templates.apply_templates` | POST | put templates on many units: `units` (JSON list) or `property` (+ `only_available=1`), and any of `payment_plan_template`, `maintenance_plan_template`, `maintenance_start_date`. `""` clears, omitted = untouched |

Template precedence on a booking: booking → unit → property → the built-in
10/20/20/25/25 plan. Maintenance starts billing on the day the booking is
confirmed (anything already due is invoiced then), then nightly.

---

## 15. Plot layout and maps

| Endpoint | Method | Does |
|---|---|---|
| `layout.get_layout` | GET | `property` → `property` (layout image, world size, annotations), `units` (shape, x, y, w, h, rotation, points, status, price, customer), `status_colors`, `can_write` — everything to draw the site plan |
| `layout.save_layout` | POST | `property`, `units: [{name, layout_shape: Rect/Polygon/Circle, layout_x, layout_y, layout_w, layout_h, layout_rotation, layout_points}]`, `world: {width, height, layout_image}`, `annotations` (free drawing layer). Needs write on the property |
| `layout.site_map` | GET | `project` / `property`, `availability` → properties and units with coordinates plus a `color` per unit, for Google Maps / Leaflet pins; `units_without_location` counts the rest |
| `layout.resolve_location` | GET | `query` = coordinates (`12.97, 77.59`), any Google Maps link (short `maps.app.goo.gl` too) or a place name → `results: [{label, latitude, longitude}]` |
| `layout.set_location` | POST | `doctype` (Property / Property Unit), `name`, and `latitude` + `longitude` or `query` (first match used) → saved with the map link |
| `layout.get_layout?property_unit=` | GET | same, for the unit's property, with `focus` = that unit |
| `layout.project_layouts?project=` | GET | every property of the project with `units`, `placed`, `has_image` — the project's Layout tab |
| `layout.editor_assets` | GET | `{js, css}` of the site's PlotLayoutEngine (the desk / portal editor) for the app to load; usage in `CRM_APP_GUIDE.md` §5.8 |
| `layout.set_unit_shape` | POST | one plot: `property_unit, layout_shape, layout_x, layout_y, layout_w, layout_h, layout_rotation, layout_points` |
| `layout.clear_unit_shape` | POST | `property_unit` — take it off the layout |

To upload a new layout image: `files.attach(doctype="Property", name, fieldname="layout_image", …)`, then `get_layout` again.

`save_layout` writes exactly the units it is sent; send every unit (the
engine's `getLayoutPayload()` does) so a plot removed in the editor goes out
as `layout_shape: ""`.

---

### Booking form auto-fill — `bookings.prefill`

`GET bookings.prefill?opportunity=` (or `property_unit=` + `customer=`) before
the booking form is shown, and again when the agreement value
(`total_price=`), plan (`payment_plan_template=`) or booking amount
(`booking_amount=`) is changed. Returns `unit_base_price`, `total_price` (+
`total_price_source`: `given` / `opportunity` / `unit_base_price`, and
`discount`), `payment_plan_template`, `booking_amount` (what was sent, else
`suggested_booking_amount` = the first milestone), `booking_date`, the
`schedule` exactly as submit will create it, unit info and customer. Nothing
is saved.

`opportunities.convert_to_booking` now takes the opportunity's
`opportunity_amount` as the agreement value when none is sent, instead of
always the unit's list price.

---

## 16. Money — invoices and payments

```
booking confirmed -> payment plan (one row per milestone)
milestone         -> billing.generate_invoice     -> Sales Invoice (submitted)
invoice           -> billing.record_payment       -> Payment Entry (submitted)
anything extra    -> billing.create_invoice       -> ad-hoc charge
```

Raising and collecting need create/submit on Sales Invoice / Payment Entry —
Property Manager and ERPNext's Accounts roles have it, sales staff only read.
Hide the buttons off `whoami.permissions`.

| Endpoint | Method | Does |
|---|---|---|
| `billing.options` | GET | `modes_of_payment [{name, type}]`, `default_items`, `charge_items` (non-stock sales items for ad-hoc charges), `company`, `currency` |
| `billing.get_invoices` | GET | `customer`, `booking` (every invoice of that deal: milestones, late fees, maintenance and ad-hoc charges on its unit), `property_unit`, `status`, `overdue=1`, `from_date` / `to_date`, `search`, paging |
| `billing.get_invoice` | GET | invoice + the `milestone` it bills + `payments` against it |
| `billing.statement` | GET | `booking` → the deal's ledger: `plan`, `plan_totals`, `invoices`, `payments`, `billed`, `outstanding`, `unbilled` |
| `billing.generate_invoice` | POST | `payment_plan` → invoice for that milestone (idempotent) |
| `billing.generate_due_invoices` | POST | `booking`, `upto_date` (default today) → invoices every due, un-billed milestone. Returns `raised`, `failed` |
| `billing.create_invoice` | POST | `booking` (or `customer` + `property_unit`), `items: [{item_code?, rate, qty, description}]` (item defaults to the Default Sale Item), `due_date`, `remarks`, `submit=1` |
| `billing.submit_invoice` / `cancel_invoice` | POST | `name` (+ `reason`). Cancelling a milestone invoice puts the milestone back to un-billed |
| `billing.record_payment` | POST | `amount*`, `mode_of_payment*`, and one of: `invoice` (against it) · `booking` (spread over its open invoices, earliest due first; anything left stays as an advance) · `customer` (advance, e.g. token money). `reference_no` + `reference_date` are required for bank / UPI / cheque modes. `posting_date`, `remarks`, `submit=1`. `tds_amount` = TDS the buyer deducted (194-IA): `amount` is what reached the bank, the invoice is settled for amount + TDS. Returns `allocated: [{invoice, amount}]` and `advance` |
| `billing.tds_suggestion` | GET | `invoice` or `booking` → `applies`, `rate`, `tds_amount`, `amount` (to bank) for what is outstanding |
| `billing.get_payments` | GET | `customer`, `booking`, `invoice`, dates, paging |
| `billing.get_payment` / `cancel_payment` | GET / POST | `name` |

Money handed over in person (cash, cheque, NEFT, UPI, loan disbursement) is
`record_payment`. To have the customer pay online — a link to send on
WhatsApp, or the gateway's checkout at the counter — use
`property_core.api.payments` (`options`, `start`, `confirm`, `status`); it works
with whichever gateway is enabled, or tells you none is. See
`PAYMENT_INTEGRATION.md` section 0.

Each instalment row (`bookings.payment_plan`) carries `payment_status`
(Pending / Invoiced / Partly Paid / Paid / Overdue / Cancelled), `paid_amount`
and `outstanding_amount`, kept in step with its invoice whichever way it was
paid.

---

## 17. After the sale — agreement and allocation

| Endpoint | Method | Does |
|---|---|---|
| `allocations.create_from_booking` | POST | `booking` (confirmed), `allocation_type` (Sale / Lease / Rental / Assignment), `start_date`, `signed_date`, `security_deposit_amount`, `with_agreement=1`, `submit=1` → **agreement + allocation in one step**; unit becomes Allocated (sale) or Leased. Idempotent |
| `allocations.get_allocations` | GET | `customer`, `property_unit`, `booking`, `status`, `allocation_type`, paging |
| `allocations.get_allocation` | GET | `name` |
| `allocations.create_allocation` / `update_allocation` | POST | `data: {customer, property_unit, allocation_type, start_date, end_date, booking, agreement, rent_amount, billing_frequency, billing_day}`; create takes `submit` |
| `allocations.submit_allocation` | POST | hand over |
| `allocations.cancel_allocation` | POST | `name`, `reason` → Terminated, unit back to Available |
| `allocations.renew_lease` | POST | `name`, `new_end_date`, `escalation_percent` |
| `allocations.get_agreements` | GET | `customer`, `property_unit`, `status`, `agreement_type` |
| `allocations.get_agreement` / `create_agreement` / `update_agreement` | GET / POST | `data: {agreement_type, customer, property_unit, agreement_status, start_date, end_date, signed_date, security_deposit_amount, document_attachment}` |
| `allocations.record_security_deposit` / `refund_security_deposit` | POST | `name` → Journal Entry |

---

## 18. Files and Drive

**Attachments** — the paperclip on any record (Lead, Opportunity, Customer,
Property Booking, Property, Property Unit, Project, Task, Property Allocation,
Property Agreement, Property Follow Up, Sales Invoice, Payment Entry, Work
Order, Issue).

| Endpoint | Method | Does |
|---|---|---|
| `files.attach` | POST | `doctype`, `name`, and the file as multipart `file` **or** `filename` + `content` (base64, a `data:` URL is fine). `fieldname` also puts it into an Attach field (`layout_image`, `document_attachment` …). `is_private=1` default. Max 25 MB |
| `files.get_attachments` | GET | `doctype`, `name` → `[{name, file_name, file_url, file_size, is_private}]` |
| `files.remove_attachment` | POST | `name` (the File id) |

Private `file_url`s (`/private/files/…`) download with the same
`Authorization: token …` header.

**Drive** — each Property has JD's folder tree (01 - Land & Legal … 09 -
Handover); each confirmed booking gets `06 - Sales & CRM / Booking Documents /
<property> - <unit>`. Reach them through the record:

| Endpoint | Method | Does |
|---|---|---|
| `files.drive_folder` | GET | `doctype` (Property / Property Booking / Property Unit / Project), `name`, `create=1` → `{folder, title, team, open_url}`; builds the tree if missing |
| `files.drive_list` | GET | `doctype`, `name`, `folder` (optional, a subfolder) → `folder`, `breadcrumbs`, `items [{name, title, is_group, mime_type, file_size, download_url}]` |
| `files.drive_create_folder` | POST | `doctype`, `name`, `title`, `parent` (optional) |
| `files.drive_upload` | POST | `doctype`, `name`, `folder` (optional), file as multipart `file` or `filename` + base64 `content` |

A folder is only reachable through a record the caller can read, and only
inside that record's own tree — any other folder id is refused. Drive's own
rules also apply: the login needs a Drive team with access (JD staff already
use Drive on the desk). `drive: false` means Drive is not installed on the site.

---

## 19. Comments, assignment, timeline — on any record

Same doctypes as attachments.

| Endpoint | Method | Does |
|---|---|---|
| `activity.add_comment` | POST | `doctype`, `name`, `text` |
| `activity.get_comments` | GET | `doctype`, `name` |
| `activity.timeline` | GET | comments, assignments, attachments, field changes (`changes: [{field, from, to}]`), calls / emails / WhatsApp — newest first |
| `activity.assign` | POST | `doctype`, `name`, `user`, `note` — one working owner |
| `activity.unassign` | POST | `doctype`, `name`, `user` |
| `activity.my_assignments` | GET | everything assigned to me, across records (`status`, `reference_type`, paging) |

---

## 20. Operations — complaints and site work

| Endpoint | Method | Does |
|---|---|---|
| `operations.get_issues` / `get_issue` | GET | `customer`, `property_unit`, `status`; one issue comes with its `work_orders` |
| `operations.create_issue` / `update_issue` | POST | `data: {subject, status, priority, customer, raised_by, description, issue_type, property_unit}` |
| `operations.get_work_orders` / `get_work_order` | GET | `property_unit`, `status`, `mine=1`, `assigned_to` |
| `operations.create_work_order` / `update_work_order` | POST | `data: {property_unit, work_type, status, issue, assigned_to, vendor, scheduled_date, completed_date, progress, description, estimated_cost, actual_cost, notes}` |
| `operations.options` | GET | statuses / types / priorities for both |

---

## 20a. Maintenance visits — `maintenance.*`

A **Property Maintenance Task** opens by itself N days before each
maintenance date on a unit's Maintenance Plan Template (Property Core
Settings: `maintenance_task_lead_days` default 3, `maintenance_task_assignee`,
`maintenance_proof_required` default on). One task per unit per period,
linked to that period's invoice. It is also opened when a booking is
confirmed, if a visit falls inside the window. This replaces the Work Order
the billing run used to open (which never saved on JD).

| Endpoint | Method | Does |
|---|---|---|
| `maintenance.summary` | GET | `open, in_progress, overdue, due_this_week, completed_this_month, lead_days, proof_required` (`property`, `project`) |
| `maintenance.get_tasks` | GET | `property_unit, property, project, customer, status, mine=1, assigned_to, overdue=1, from_date, to_date, search`, paging; rows carry `overdue`, `assigned_to_name` |
| `maintenance.get_task` | GET | task + `updates[] {update_type, progress, note, posted_on, posted_by_name, proof[] {name, file_name, file_url, kind}}`, `task_files`, `proof_count`, `proof_required` |
| `maintenance.create_task` | POST | off-schedule visit: `data: {property_unit*, subject, scheduled_date, assigned_to, description, show_to_customer}` |
| `maintenance.update_task` | POST | `name, data` — same fields |
| `maintenance.assign` | POST | `name, user` (desk ToDo follows) |
| `maintenance.post_update` | POST | `name, note, progress, update_type` (Progress / Blocked / Note) + proof: multipart `file` (repeat) or `files: [{filename, content}]` base64. Open → In Progress |
| `maintenance.complete` | POST | `name, work_done` + optional proof in the same call. Refused without any proof when proof is required |
| `maintenance.cancel` / `reopen` | POST | `name, reason` |
| `maintenance.unit_history` | GET | `property_unit` → `schedule` (charges billed / to come) + `tasks` with updates and proof + counts |
| `maintenance.generate_now` | POST | `property_unit` or `property` — open whatever is due in the window now |

Desk: Property Maintenance Task form has **Post Update** (then attach photos)
and **Mark Completed**; the unit form lists every visit under the maintenance
schedule.

---

## 21. The whole flow, end to end

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
11. billing.generate_invoice               -> first milestone billed
12. billing.record_payment                 -> money in, spread over open invoices
13. allocations.create_from_booking        -> agreement + unit handed over
14. files.drive_upload                     -> signed papers into the booking's folder
15. dashboard.flow / projects.overview     -> the business, updated
```

Before step 3, once per development: `projects.create_project` →
`inventory.create_property` → `inventory.bulk_create_units` →
`templates.save_payment_template` / `save_maintenance_template` →
`templates.apply_templates` → `layout.save_layout`.

Every step above is covered by the automated suites, run against
`review.site`:

| suite | what it proves |
|---|---|
| `property_core/tests/crm_api_smoke.py` | the funnel end to end, 38 assertions |
| `property_core/tests/crm_api_coverage.py` | the remaining endpoints, 60 assertions |
| `property_core/tests/crm_data_verify.py` | what actually reached the database — address, contact, payment plan, unit status, portal login — 51 assertions |
| `property_core/tests/crm_masters_check.py` | dropdown masters: new values usable at once, disable, hide-from-sales, refusal of unknown values, inventory create — 60 assertions |
| `property_core/tests/crm_maintenance_check.py` | maintenance: task opened ahead of the date, proof required, updates, unit history, portal view + proof streaming + portal documents / Drive / handover / extra charges — 41 + 14 assertions |
| `property_core/tests/crm_backend_check.py` | dashboards, tasks, templates, bulk units, layout/map, invoice → payment → allocation, attachments, Drive, comments, operations, and what an executive is refused — 97 assertions |

---

## 22. Notes for the app

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
