# CRM App — frontend implementation guide

This guide is organised by screen. For each screen it says which API to call,
when to call it (on screen load, when a field changes, when a button is
pressed), what to send and what comes back. The field-by-field reference for
every endpoint is in `CRM_API.md`; the full list is the index at the end of
this file.

**Two rules for the app:**

1. **Nothing is hardcoded except buttons and colours.** Every dropdown value,
   default and label comes from the API (see [§3 Dropdowns](#3-dropdowns--where-every-option-list-comes-from)).
2. **Anything that can be derived is derived by the server.** Pick a unit and
   the server knows its property, project, price and plan. Call the
   auto-fill endpoint to show those values (see [§4 Auto-fill](#4-auto-fill--what-to-call-when-a-field-changes)).
   Never ask the user to type them.

---

## 1. Calling the API

```
Base:     https://<site>/api/method/property_core.api.crm.<module>.<function>
Auth:     Authorization: token <api_key>:<api_secret>      (from session.login)
Reads:    GET  with query-string args
Writes:   POST with JSON body  (Content-Type: application/json)
Payload:  response.message.data
Message:  response.message.message   (a sentence to toast after a write, may be null)
```

The app reads `response.message.data` in every case:

```json
{"message": {"status": "ok", "message": "Lead CRM-LEAD-2026-00066 created", "data": {"name": "CRM-LEAD-2026-00066"}}}
```

**Errors** come back as HTTP 4xx/5xx. Show the user
`JSON.parse(JSON.parse(body._server_messages)[0]).message`. Branch on
`body.exc_type`:

| `exc_type` | What to do |
|---|---|
| `AuthenticationError` | token gone → back to login |
| `PermissionError` | hide the action; this user may not do it |
| `ValidationError` / `MandatoryError` | show the message next to the form |
| `DoesNotExistError` | record deleted or not visible to this user |

**Lists** all take `page` (from 1) and `page_size` (max 100), and return
`{rows, page, page_size, total, has_more}`. Use `has_more` for "load more".
Don't compare row counts.

**Record args** go either inside `data: {...}` or as top-level keys; both
work. Fields the endpoint does not accept are ignored silently, so sending a
whole record back on save is safe.

**File uploads** (attachments, Drive, maintenance proof) accept either
multipart `file` (repeat the field for many) or JSON base64:
`{"filename": "site.jpg", "content": "<base64 or data:… URL>"}`.
Max 25 MB per file.

---

## 2. App start — four calls, then cache

| # | Call | Why | Keep |
|---|---|---|---|
| 1 | `POST session.login {usr, pwd}` | returns `api_key` / `api_secret` → store as the token | token |
| 2 | `GET session.whoami` | who, `scope` (`all`/`team`/`own`), `roles`, `team`, **`permissions`** per doctype, `defaults` (company, currency, date format) | whole object |
| 3 | `GET meta.options` | **every dropdown and default** the core screens need | whole object |
| 4 | `GET team.assignable_users` | the people this login may assign work to (`[{user, full_name}]`) | list |

Fetch these once per screen, when the screen first opens:
`billing.options` (payment modes, charge items), `tasks.options`,
`operations.options`, `templates.get_payment_templates`,
`templates.get_maintenance_templates`.

**Show or hide buttons from `whoami.permissions`, not from role names:**

```js
const can = (doctype, action) => me.permissions?.[doctype]?.[action];
can("Sales Invoice", "create")    // "Generate invoice" button
can("Payment Entry", "create")    // "Record payment"
can("Property Unit", "write")     // "Edit unit", layout "Edit"
can("Property Maintenance Task", "write")   // "Post update" / "Complete"
```

`whoami` sample (trimmed):

```json
{
 "user": "crmadmin@test.local", "full_name": "CRM Admin",
 "scope": "all", "is_admin": true, "is_manager": false, "property_role": "Property Manager",
 "team": ["crmmanager@test.local", "crmexec1@test.local"],
 "permissions": {
   "Lead": {"read": true, "write": true, "create": true, "delete": true, "submit": false, "cancel": true},
   "Sales Invoice": {"read": true, "write": true, "create": true, "delete": false, "submit": true, "cancel": true}
 },
 "defaults": {"company": "TP Private Limited", "currency": "INR", "date_format": "dd-mm-yyyy", "time_zone": "Asia/Kolkata"}
}
```

---

## 3. Dropdowns — where every option list comes from

| Field on screen | Source | Key |
|---|---|---|
| Lead status | `meta.options` | `lead.statuses` (working ones: `lead.working_statuses`; colour: `lead.status_details[].indicator`) |
| Lead source | `meta.options` | `lead.sources` |
| Unit type wanted / unit type | `meta.options` | `lead.unit_types` / `unit.types` |
| Facing | `meta.options` | `lead.facings` / `unit.facings` |
| Opportunity status / type / stage / source | `meta.options` | `opportunity.statuses` / `.types` / `.stages` / `.sources` |
| Follow-up type / outcome / status | `meta.options` | `follow_up.types` / `.outcomes` / `.statuses` |
| Booking status (filter) | `meta.options` | `booking.statuses` |
| Payment plan | `meta.options` | `booking.payment_plan_templates` (details: `templates.get_payment_templates`) |
| Sales person | `meta.options` | `booking.sales_persons` (may be empty — then hide the field) |
| Unit availability (filter) | `meta.options` | `unit.availability` |
| Property type / status | `meta.options` | `property.types` / `property.statuses` |
| Company | `meta.options` | `company` |
| Any field's default value | `meta.options` | `defaults["<same key>"]`, e.g. `defaults["lead.statuses"]` = `"New"` |
| Owner / assign to / assignee | `team.assignable_users` | `[{user, full_name}]` |
| Property (picker) | `inventory.get_properties?search=&page_size=50` | `rows[].name`, `property_name`, `units.available` |
| Unit (picker, sellable only) | `inventory.available_units?property=<p>&search=` | `rows[]` (Available + Reserved) |
| Unit (picker, any) | `inventory.get_units?property=<p>` | `rows[]` |
| Project | `projects.get_projects?search=&with_stats=0` | `rows[].name`, `project_name` |
| Customer | `customers.get_customers?search=` | `rows[].name`, `customer_name`, `mobile_no` |
| Lead (picker) | `leads.get_leads?search=` | `rows[]` |
| Maintenance template | `templates.get_maintenance_templates` | `[].name` |
| Mode of payment | `billing.options` | `modes_of_payment[] {name, type}` — `type: "Bank"` means reference no. + date are required |
| Extra-charge item | `billing.options` | `charge_items[]`, default `default_items.sale` |
| Task status / priority / type | `tasks.options` | `statuses` / `priorities` / `types` |
| Issue status / priority / type; work order status / type | `operations.options` | `issue.*` / `work_order.*` |
| Allocation type | fixed by ERP: `Sale`, `Lease`, `Rental`, `Assignment` | — |
| Manual unit status | fixed: `Available`, `Reserved`, `Maintenance Blocked` | — |
| Maintenance update type | fixed: `Progress`, `Blocked`, `Note` | — |

**"+ Add new value" in a dropdown.** `meta.options.masters` maps each list to
the master doctype that stores it (e.g. `lead.sources` → `Lead Source`).
Admins add values there, and the next `meta.options` call returns them.

---

## 4. Auto-fill — what to call when a field changes

| When the user… | Call | Fill in |
|---|---|---|
| picks a **unit** anywhere (lead, opportunity, form) | `GET inventory.resolve_unit?property_unit=U` | property, property_name, project, unit_type, area, facing, base_price, availability_status, payment_plan_template |
| opens **New booking** from an opportunity | `GET bookings.prefill?opportunity=O` | unit info, **`unit_base_price`**, **`total_price`** (agreed value), `payment_plan_template`, suggested `booking_amount`, `booking_date`, `schedule[]`, customer |
| opens **Walk-in booking** / picks a unit on it | `GET bookings.prefill?property_unit=U&customer=C` | same as above |
| edits **agreement value** or **payment plan** on the booking form | `GET bookings.prefill?...&total_price=X&payment_plan_template=T` | `booking_amount`, `schedule[]` (the plan the customer signs up for) |
| types a **mobile number** on New lead | `GET leads.find_duplicates?mobile_no=…` | "already exists" warning |
| picks a **unit** on an opportunity | `POST opportunities.set_property {name, property_unit}` | server fills property + project; a unit from another property is refused |
| wants the customer to see a **payment plan** before booking | `GET templates.preview_payment_plan?property_unit=U` (or `amount` + `template`) | schedule table |
| picks a **mode of payment** | look up `type` in `billing.options.modes_of_payment` | show reference no. + date inputs when `type == "Bank"` |
| pastes a **Google Maps link** / types a place | `GET layout.resolve_location?query=…` | candidate `{latitude, longitude, label}` |

`bookings.prefill` response (real, trimmed):

```json
{
 "property_unit": "UNIT-0055", "unit_number": "S272931-2",
 "unit_property": "CRM Smoke Property", "project": "PROJ-0003",
 "unit_type": "Plot", "unit_area": 1202.0, "availability_status": "Available", "bookable": true,
 "unit_base_price": 2700000.0,
 "total_price": 2600000.0, "total_price_source": "opportunity", "discount": 100000.0,
 "payment_plan_template": "Luxury Villa Split",
 "booking_amount": 130000.0, "booking_date": "2026-09-29",
 "schedule": [
   {"milestone": "Token", "percentage": 5.0, "due_date": "2026-09-29", "amount": 130000.0},
   {"milestone": "On Agreement", "percentage": 15.0, "due_date": "2026-10-29", "amount": 390000.0}
 ],
 "customer": null, "lead": "CRM-LEAD-2026-00061", "customer_will_be_created": true
}
```

`total_price_source` is `given` / `opportunity` / `unit_base_price`. Show it
as a hint under the field, e.g. "From the opportunity · ₹1 L below base
price". Show `unit_base_price` as a read-only field next to it.

---

## 5. Screens

### 5.1 Home / Business flow dashboard

**Where:** app home. **Why:** the whole business, lead to money, in one call.

| Part | Call |
|---|---|
| Filter bar | `view_type` = `my` / `team` / `organisation`; `date_range` = `all`/`today`/`yesterday`/`week`/`month`/`custom` (+ `date_from`, `date_to`); `team_member` = comma list; `project` |
| Pipeline, KPIs, money, inventory | `GET dashboard.flow?view_type=organisation&date_range=month` |
| Lead status / source bars | `GET dashboard.lead_dashboard?...same filters` |
| 6-month chart | `GET dashboard.trend?view_type=…&months=6` |
| Today's agenda | `GET follow_ups.my_agenda` |
| Team switcher | `team_members[]` in any dashboard response (`[{user_id, name}]`) |

Hide the `team` / `organisation` options when `user_type == "regular"`
(an executive). The server returns empty numbers for them anyway.

`dashboard.flow` → `stages[]` drives the funnel strip:
`[{"stage": "Leads", "count": 60}, {"stage": "Opportunities", "count": 50}, …]`.
Money cards: `money.collected`, `money.outstanding`, `money.overdue`, `money.due_next_30_days`.
Conversion: `conversion.lead_to_opportunity` (%), `.opportunity_to_booking`,
`.lead_to_booking`, `.collection_rate`.

> **Migrating from JD's old script:** the old call was
> `/api/method/get_dashboard_data?view_type=my`. The new call is
> `…crm.dashboard.lead_dashboard?view_type=my`. The params and keys are the
> same, but the payload is now at `message.data` and the data comes from
> ERPNext **Lead** (not CRM Lead).

### 5.2 Leads

| Action | Call | Payload |
|---|---|---|
| List + filters | `GET leads.get_leads` | `search, status, source, owner, property, project, unit_type, from_date, to_date, mine=1, page, page_size` |
| Status chips above list | `GET leads.pipeline` | → `by_status[{status,total}]` |
| Open | `GET leads.get_lead?name=` | lead + `follow_ups`, `opportunities`, `bookings`, `activity`, `assigned_to` |
| New | `POST leads.create_lead` | `{"data": {"lead_name":"Ravi K","mobile_no":"9876543210","custom_lead_source":"Website","custom_lead_status":"New","custom_unit_type":"Plot","custom_budget":3000000,"city":"Bengaluru"}}` |
| Edit | `POST leads.update_lead` | `{"name":"CRM-LEAD-…","data":{...}}` |
| Change status | `POST leads.set_status` | `{name, status, notes}` |
| Assign | `POST leads.assign_lead` | `{name, user, note}` — moves the follow-up owner and the ToDo |
| Hand over | `POST leads.transfer_ownership` | `{name, user}` |
| → Opportunity | `POST leads.convert_to_opportunity` | `{name, property_unit, opportunity_amount?, expected_closing?, next_follow_up_on?, notes?}` — idempotent |
| → Customer | `POST leads.create_customer` | `{name}` — keeps the address |

### 5.3 Follow-ups

| Action | Call | Payload |
|---|---|---|
| List | `GET follow_ups.get_follow_ups` | `reference_doctype, reference_name, status, assigned_to, follow_up_type, from_date, to_date, mine` |
| Schedule | `POST follow_ups.create_follow_up` | `{reference_doctype:"Lead", reference_name, follow_up_type, scheduled_on:"2026-10-01 11:00:00", assigned_to?, notes?}` |
| Log a call that happened | `POST follow_ups.log_follow_up` | `{reference_doctype, reference_name, follow_up_type, outcome, notes, next_follow_up_on?}` — `next_follow_up_on` chains the next one |
| Done | `POST follow_ups.complete_follow_up` | `{name, outcome, notes, next_follow_up_on?}` |
| Move | `POST follow_ups.reschedule` | `{name, scheduled_on, notes}` |

### 5.4 Opportunities

| Action | Call | Payload |
|---|---|---|
| List | `GET opportunities.get_opportunities` | `search, status, property, project, property_unit, owner, mine` |
| Open | `GET opportunities.get_opportunity?name=` | + `unit`, `follow_ups`, `bookings`, `can_book` |
| Walk-in | `POST opportunities.create_opportunity` | `{"data":{"opportunity_from":"Customer","party_name":"CUST-…","custom_property_unit":"UNIT-…","opportunity_amount":2600000}}` |
| Tag unit | `POST opportunities.set_property` | `{name, property_unit}` |
| Lost / other status | `POST opportunities.set_status` | `{name, status, reason}` |
| **Book** | first `GET bookings.prefill?opportunity=O` to fill the form, then `POST opportunities.convert_to_booking` | `{name, booking_amount, total_price, payment_plan_template, booking_date, sales_person?, notes?, submit: 0/1}` |

### 5.5 Booking — create

Form fields and where they come from:

| Field | Source | Editable |
|---|---|---|
| Unit info line | `bookings.prefill` | no |
| **Unit base price** | `bookings.prefill.unit_base_price` | no |
| **Agreement value** | `bookings.prefill.total_price` | yes — re-call prefill with `total_price` |
| Payment plan | `bookings.prefill.payment_plan_template` (options: `meta.options.booking.payment_plan_templates`) | yes — re-call prefill |
| Booking amount | `bookings.prefill.booking_amount` (first milestone) | yes |
| Schedule preview | `bookings.prefill.schedule` | no |
| Customer | from opportunity / lead; walk-in: pick with `customers.get_customers` | walk-in only |

Save: `POST bookings.create_booking {"data": {customer, property_unit, total_price, booking_amount, booking_date, payment_plan_template, sales_person?, notes?}, "submit": 0}`.
From an opportunity, use `opportunities.convert_to_booking` instead; it
creates the customer from the lead if needed.

**Confirm** (`POST bookings.submit_booking {name}`) reserves the unit, raises
the payment plan, creates the customer's portal login, opens the Drive folder
and starts maintenance billing.

### 5.6 Booking — detail (the deal's workspace)

| Section / button | Call |
|---|---|
| Header, unit, plan, collections | `GET bookings.get_booking?name=` |
| Statement (plan + invoices + payments) | `GET billing.statement?booking=` |
| "Invoice" on a plan row | `POST billing.generate_invoice {payment_plan}` |
| "Invoice all due" | `POST billing.generate_due_invoices {booking}` |
| "+ Extra charge" | `POST billing.create_invoice {booking, items:[{item_code?, rate, description}], due_date?, submit:1}` |
| "Record payment" | `POST billing.record_payment {booking, amount, mode_of_payment, reference_no?, reference_date?, posting_date?}` → `allocated[]` + `advance` |
| "Allocate unit" (handover) | `POST allocations.create_from_booking {booking, allocation_type:"Sale", start_date, signed_date?, security_deposit_amount?}` |
| Files tab | `GET files.get_attachments?doctype=Property Booking&name=` / `POST files.attach` / `POST files.remove_attachment {name}` |
| Drive tab | `GET files.drive_list?doctype=Property Booking&name=&folder=` / `POST files.drive_upload` / `POST files.drive_create_folder` |
| Timeline + comments | `GET activity.timeline?doctype=Property Booking&name=` / `POST activity.add_comment` |
| Cancel | `POST bookings.cancel_booking {name, reason}` → unit back to Available |

`record_payment` examples:

```json
{"booking": "BKG-0091", "amount": 300000, "mode_of_payment": "Cash"}
{"invoice": "ACC-SINV-2026-00186", "amount": 25000, "mode_of_payment": "Bank Draft",
 "reference_no": "UTR88213", "reference_date": "2026-09-29"}
{"customer": "CUST-2026-00031", "amount": 50000, "mode_of_payment": "Cash"}
```

The response shows where the money went:

```json
{"name": "ACC-PAY-2026-00012", "paid_amount": 300000.0,
 "allocated": [{"invoice": "ACC-SINV-2026-00175", "amount": 10000.0},
               {"invoice": "ACC-SINV-2026-00176", "amount": 220000.0}],
 "advance": 70000.0}
```

### 5.7 Project → Property → Unit setup (inventory)

Do these in order, once per development:

1. `POST projects.create_project {"data":{"project_name":"Prashantha Vana","expected_start_date":"2026-10-01"}}`
2. `POST inventory.create_property {"data":{"property_name":"PV Phase 1","property_type":"Township","project":"PROJ-0007"}}`
3. `POST inventory.bulk_create_units {"property":"PV Phase 1","prefix":"A-","start":1,"count":40,"defaults":{"unit_type":"Plot","area":1200,"base_price":1500000,"facing":"East"}}` (safe to re-run; returns `created`, `skipped`)
4. `POST templates.save_payment_template {"template_name":"PV 10-20-70","milestones":[{"milestone":"Booking","percentage":10,"offset_months":0},{"milestone":"Agreement","percentage":20,"offset_months":1},{"milestone":"Registration","percentage":70,"offset_months":3}]}`
5. `POST templates.save_maintenance_template {"template_name":"PV Upkeep","schedule":[{"month_no":1,"description":"Corpus fund","amount":25000}],"repeat_every_n_months":1,"repeat_amount":1500}`
6. `POST templates.apply_templates {"property":"PV Phase 1","payment_plan_template":"PV 10-20-70","maintenance_plan_template":"PV Upkeep"}`
7. Layout: see §5.8.

The project screen's tabs: `projects.overview` (everything),
`projects.project_inventory`, `project_funnel`, `project_bookings`,
`project_operations`, `project_activity`, **`layout.project_layouts`**,
`tasks.get_tasks?project=`.

Unit screen: `inventory.get_unit`, edit with `inventory.update_unit`,
hold/block with `inventory.set_unit_status {name, status, reason}`,
maintenance history with `maintenance.unit_history`, "show on layout" with
`layout.get_layout?property_unit=`.

### 5.8 Plot layout — view and edit (inside Project / Property / Unit)

The site already has a full SVG layout editor, the same one the desk editor
and the customer-portal map use. The app loads it instead of building its own.

```js
const a = (await get("layout.editor_assets"));           // {js, css, shapes}
loadCss(SITE + a.css); await loadScript(SITE + a.js);    // public files, no auth needed
const engine = new PlotLayoutEngine(el, {
  mode: "view",                        // "edit" after the user taps Edit (needs can_write)
  grid: 10,                            // snap; 0 = off
  onSelect: unit => showUnitCard(unit),
  onChange: () => markDirty(),
  onDrawComplete: shape => engine.assignShape(pendingUnit, shape),
  tooltipHtml: u => `${u.unit_number} · ${u.availability_status}`,
});
const d = await get("layout.get_layout", {property});    // or {property_unit} to open at that unit
engine.setData(d);                                       // d.focus = unit to zoom to
```

| User action | Engine call |
|---|---|
| Edit / Done | `engine.setMode("edit" \| "view")` (show Edit only if `d.can_write`) |
| Draw plot for an unplaced unit | `pendingUnit = u.name; engine.startDraw("rect" \| "polygon" \| "circle")` → `onDrawComplete` → `engine.assignShape(u.name, shape)` |
| Move / resize / rotate / reshape | drag the plot / its handles (built in) |
| Remove plot from layout | `engine.removeShape(name)` |
| Text / pencil / eraser / marker | `engine.startDraw("text" \| "pencil" \| "eraser" \| "emoji")` (`onTextRequest(pt)` asks for the text) |
| Zoom | `engine.zoomBy(1.3)`, `engine.zoomToFit()`, `engine.focusUnit(name)` |
| Units list | `engine.units` (`shape` null = not on the layout yet) |
| Save | `POST layout.save_layout {property, units: engine.getLayoutPayload(), world: {width, height}, annotations: engine.getAnnotations()}` |
| Blueprint image | `POST files.attach {doctype:"Property", name, fieldname:"layout_image", is_private:0, filename, content}` then `engine.setImage(url, naturalW, naturalH)` and save |
| One plot only (no full editor) | `POST layout.set_unit_shape {property_unit, layout_shape:"Rect", layout_x, layout_y, layout_w, layout_h, layout_rotation}` / `layout.clear_unit_shape` |

Shape geometry: Rect = top-left `x,y` + `w,h` + rotation (degrees, about the
centre). Circle = centre `x,y`, `w` = diameter. Polygon = `points: [[x,y],…]`.

**Geo map** (real map with pins): `GET layout.site_map?project=|property=` →
`units[] {latitude, longitude, color, availability_status}`. Set a pin with
`POST layout.set_location {doctype:"Property Unit", name, latitude, longitude}`
or `{…, query: "<Google Maps link or place>"}`.

### 5.9 Maintenance

Tasks open **by themselves**, N days before each maintenance date on a unit's
plan (Property Core Settings → lead days, default assignee, proof required).

| Action | Call | Payload |
|---|---|---|
| Board counts | `GET maintenance.summary?property=` | `open, in_progress, overdue, due_this_week, completed_this_month` |
| List | `GET maintenance.get_tasks` | `property_unit, property, project, status, mine=1, overdue=1, from_date, to_date` |
| Open | `GET maintenance.get_task?name=` | + `updates[] {note, progress, proof[] {file_url, kind: image\|video\|file}}`, `proof_required`, `proof_count` |
| Post progress with photos | `POST maintenance.post_update` | `{name, note:"East side cleared", progress:40, update_type:"Progress", files:[{filename:"east.jpg", content:"<base64>"}]}` |
| Complete | `POST maintenance.complete` | `{name, work_done:"Clean-up finished", files:[…]}`. Refused without proof when proof is required |
| Assign | `POST maintenance.assign {name, user}` | shows in their desk ToDo |
| Off-schedule visit | `POST maintenance.create_task {"data":{"property_unit":"UNIT-…","subject":"Fix gate","scheduled_date":"2026-10-02"}}` |
| Cancel / reopen | `POST maintenance.cancel {name, reason}` / `maintenance.reopen` |
| Unit history | `GET maintenance.unit_history?property_unit=` | charges schedule + every visit with proof |
| Open due tasks now | `POST maintenance.generate_now {property_unit}` or `{property}` |

Proof images are private files: load them with the token header
(`fetch(url, {headers: {Authorization}})` → blob URL).

### 5.10 Invoices & payments (finance screen)

`billing.get_invoices` (filters: `customer, booking, property_unit, status, overdue=1, from_date, to_date`),
`billing.get_invoice`, `billing.submit_invoice`, `billing.cancel_invoice {name, reason}`
(a milestone invoice goes back to "to bill"), `billing.get_payments`,
`billing.get_payment`, `billing.cancel_payment`.

### 5.11 Tasks (project work)

`tasks.get_tasks` (`project, status, mine=1, assigned_to, overdue=1`),
`tasks.create_task {"data":{"subject","project","exp_end_date","priority"}, "assign_to":"user@x"}`,
`tasks.set_status {name, status, note}`, `tasks.assign_task {name, user, keep_others:0}`,
`tasks.update_task`, `tasks.delete_task`.

### 5.12 After the sale

`allocations.get_allocations`, `get_allocation`, `submit_allocation`,
`cancel_allocation {name, reason}`, `renew_lease {name, new_end_date, escalation_percent}`;
agreements: `get_agreements`, `get_agreement`, `update_agreement`,
upload the signed copy with `files.attach {doctype:"Property Agreement", name, fieldname:"document_attachment", …}`,
`record_security_deposit {name}`.

### 5.13 Complaints and site work

`operations.get_issues`, `get_issue`, `create_issue {"data":{subject, customer, property_unit, description}}`,
`update_issue`; `operations.get_work_orders`, `create_work_order`, `update_work_order`.
**On JD the Work Order endpoints fail today**, because "Work Order" is also
ERPNext Manufacturing's doctype. Use maintenance tasks for maintenance until
that is renamed.

### 5.14 Any record — files, comments, assignment

Works on Lead, Opportunity, Customer, Property Booking, Property, Property
Unit, Project, Task, Property Allocation, Property Agreement, Property Follow
Up, Sales Invoice, Payment Entry, Issue, Property Maintenance Task:

`files.attach` / `get_attachments` / `remove_attachment`,
`activity.add_comment` / `get_comments` / `timeline` / `assign` / `unassign`,
`activity.my_assignments` (the "My work" inbox across all records).

---

## 6. Who sees what

Visibility is decided on the server. The app never filters for it.

| Level | Role | Sees |
|---|---|---|
| L1 sales executive | Property Sales Executive | own leads / opportunities / bookings / follow-ups (owner or assigned) |
| L2 team manager | Property Sales Manager | own + everyone under them in `Employee.reports_to`, can edit |
| L3 admin | Property Manager | everything, plus money (invoices, payments) and inventory edits |

`whoami.scope` = `own` / `team` / `all`. Every list and dashboard already
comes back scoped.

---

## 7. Endpoint index

All endpoints, generated from the code. Params with `?` are optional.
Full detail per endpoint is in `CRM_API.md`.

**164 endpoints.** Path: `/api/method/property_core.api.crm.<module>.<function>`.


#### `session` (5)

| Endpoint | What it is for |
|---|---|
| `session.login(usr, pwd)` | Authenticate a staff user and hand back an API token plus their scope. |
| `session.whoami()` | Everything the app needs to draw the right screen for this login. |
| `session.me()` | Profile screen: user, roles, employee, team, permissions (same data as whoami). |
| `session.refresh_token()` | New api_key/api_secret for the current session user. |
| `session.logout()` | Logout button: ends the session. |

#### `meta` (2)

| Endpoint | What it is for |
|---|---|
| `meta.options()` | All select options, in one payload. |
| `meta.field_options(doctype, fieldname)` | One field's Select options, for a screen built after this API shipped. |

#### `team` (3)

| Endpoint | What it is for |
|---|---|
| `team.my_team()` | The people under this login, flat and nested. |
| `team.assignable_users()` | Who this login may assign a lead or follow-up to: themselves and their team. An admin gets everyone holding a property role. |
| `team.performance(from_date?, to_date?)` | Leads / opportunities / bookings per person, for the people this login can see. Values come off the booking, so it is money agreed, not fore |

#### `dashboard` (4)

| Endpoint | What it is for |
|---|---|
| `dashboard.summary(from_date?, to_date?)` | Classic home cards: today's follow-ups, untouched leads, funnel, conversion, top projects (from_date / to_date). |
| `dashboard.lead_dashboard(view_type?, team_member?, date_range?, date_field?, date_from?, date_to?)` | Lead counts by status and source -- the exact shape JD's `/api/method/get_dashboard_data` server script returns, but read from ERPNext `L |
| `dashboard.flow(view_type?, team_member?, date_range?, date_from?, date_to?, project?)` | Overall status of the business, stage by stage: |
| `dashboard.trend(view_type?, team_member?, months?, project?)` | Month by month: new leads, opportunities, bookings, booked value and money collected -- the line chart under the flow. |

#### `leads` (11)

| Endpoint | What it is for |
|---|---|
| `leads.get_leads(search?, status?, source?, owner?, property?, project?, unit_type?, from_date?, to_date?, mine?, filters?, order_by?, page?, page_size?)` | The lead list, filtered the way the screens filter it. |
| `leads.get_lead(name)` | One lead with everything hanging off it -- the detail screen in a single round trip. |
| `leads.create_lead(data?)` | A new enquiry. `lead_owner` defaults to whoever is calling, which is also what decides who can see it afterwards. |
| `leads.update_lead(name, data?)` | Save edits to a lead — send only changed fields in `data`. |
| `leads.set_status(name, status, notes?)` | Move a lead along the pipeline. The native `status` follows through STATUS_MAP, so ERPNext's own reports stay honest. |
| `leads.assign_lead(name, user, note?)` | Hand the lead to someone. Both the follow-up owner and the ToDo move, because the desk shows one and the reminders read the other. |
| `leads.transfer_ownership(name, user)` | Give the lead away outright -- owner, follow-up owner and assignment. |
| `leads.convert_to_opportunity(name, property?, property_unit?, opportunity_amount?, expected_closing?, next_follow_up_on?, notes?)` | Lead → Opportunity, with the property tagged on the way through. |
| `leads.create_customer(name)` | Lead → Customer. A booking needs one, and ERPNext's own conversion drops the address, so the app's version is used. |
| `leads.find_duplicates(mobile_no, exclude?)` | Same number already in the system? Used by the capture form as you type. |
| `leads.pipeline(from_date?, to_date?, project?)` | Lead counts per status -- the funnel chart, scoped to what the caller may see. |

#### `follow_ups` (8)

| Endpoint | What it is for |
|---|---|
| `follow_ups.get_follow_ups(reference_doctype?, reference_name?, status?, assigned_to?, follow_up_type?, from_date?, to_date?, mine?, search?, order_by?, page?, page_size?)` | follow up list screen: paged, searchable, filter by the params shown. |
| `follow_ups.get_follow_up(name)` | Open one follow up (detail screen). |
| `follow_ups.create_follow_up(reference_doctype, reference_name, follow_up_type?, scheduled_on?, assigned_to?, notes?, status?, property?, property_unit?)` | Schedule the next touch. Party name, number and property are pulled off the reference by the doctype itself, so the client need not send the |
| `follow_ups.log_follow_up(reference_doctype, reference_name, follow_up_type?, outcome?, notes?, next_follow_up_on?, next_action?, assigned_to?)` | Record a call that already happened, and optionally book the next one. |
| `follow_ups.complete_follow_up(name, outcome?, notes?, next_follow_up_on?, next_action?)` | Close an open follow-up. A `next_follow_up_on` raises the next one automatically -- that chaining is what keeps a lead from going cold. |
| `follow_ups.reschedule(name, scheduled_on, notes?)` | "Reschedule" button on an open follow-up. |
| `follow_ups.cancel_follow_up(name, reason?)` | "Cancel" on a follow-up; `reason` is kept as a comment. |
| `follow_ups.my_agenda(date?, days?, user?)` | Overdue / today / upcoming, the way the home screen shows it. |

#### `opportunities` (8)

| Endpoint | What it is for |
|---|---|
| `opportunities.get_opportunities(search?, status?, property?, project?, property_unit?, owner?, mine?, from_date?, to_date?, filters?, order_by?, page?, page_size?)` | opportunitie list screen: paged, searchable, filter by the params shown. |
| `opportunities.get_opportunity(name)` | Open one opportunity (detail screen). |
| `opportunities.create_opportunity(data?)` | A direct opportunity — a walk-in who never was a lead, or one raised against an existing customer. |
| `opportunities.update_opportunity(name, data?)` | Save edits to a opportunity — send only changed fields in `data`. |
| `opportunities.set_property(name, property?, property_unit?)` | Tag the development and the unit. |
| `opportunities.set_status(name, status, reason?)` | Status dropdown on the opportunity (Lost needs `reason`). |
| `opportunities.convert_to_booking(name, booking_date?, booking_amount?, total_price?, payment_plan_template?, sales_person?, property_unit?, notes?, submit?)` | Opportunity → Property Booking. |
| `opportunities.funnel(from_date?, to_date?, project?)` | Opportunity counts and value per status, scoped to the caller. |

#### `customers` (4)

| Endpoint | What it is for |
|---|---|
| `customers.get_customers(search?, filters?, page?, page_size?, order_by?)` | Customer list and the customer picker (`search` = name / mobile). |
| `customers.get_customer(name)` | The customer and their whole property position. |
| `customers.create_customer(data?)` | "New customer" form; `data` = customer_name, mobile_no, email_id, customer_type, pan/gst. |
| `customers.create_from_lead(lead)` | Lead → Customer, address and contact carried over. Idempotent: calling it twice returns the customer that already exists. |

#### `bookings` (8)

| Endpoint | What it is for |
|---|---|
| `bookings.get_bookings(search?, customer?, property?, project?, property_unit?, status?, docstatus?, mine?, from_date?, to_date?, filters?, order_by?, page?, page_size?)` | booking list screen: paged, searchable, filter by the params shown. |
| `bookings.get_booking(name)` | The booking with its money attached — plan, invoices, what is paid. |
| `bookings.prefill(opportunity?, property_unit?, customer?, lead?, total_price?, payment_plan_template?)` | Everything a new-booking form should show filled in, before anything is saved: unit details and base price, the agreement value (negotiated |
| `bookings.create_booking(data?, submit?)` | A booking raised straight off a unit — the walk-in path, where nobody ever logged a lead. |
| `bookings.update_booking(name, data?)` | Save edits to a booking — send only changed fields in `data`. |
| `bookings.submit_booking(name)` | Confirm the deal: the unit is reserved, the payment plan is raised, the customer gets a portal login and maintenance starts. |
| `bookings.cancel_booking(name, reason?)` | Cancelling puts the unit back on the market. |
| `bookings.payment_plan(booking)` | Booking "Payment plan" tab: milestone rows with invoice + paid status, and totals. |

#### `inventory` (13)

| Endpoint | What it is for |
|---|---|
| `inventory.create_property(data?)` | A new property. `property_type` is a Property Type record, so a new kind of property is a new record, not a code change. |
| `inventory.create_unit(data?)` | A new unit under an existing property; project comes off the property. |
| `inventory.update_property(name, data?)` | Change a property. `amenities` / `property_documents` replace the whole table: `[{"amenity_name": "Clubhouse", "amenity_type": "Recreat |
| `inventory.update_unit(name, data?)` | Change a unit. `availability_status` is not taken here -- use `set_unit_status`; bookings and allocations move it themselves. |
| `inventory.set_unit_status(name, status, reason?)` | Hold, release or block a unit by hand (Available / Reserved / Maintenance Blocked). A unit with a live booking or allocation cannot be moved |
| `inventory.bulk_create_units(property, units?, prefix?, start?, count?, defaults?)` | Lay out many units in one go -- either an explicit JSON list of `units` (each like create_unit's data), or `count` numbered units `{pre |
| `inventory.get_properties(project?, search?, status?, property_type?, page?, page_size?, order_by?)` | Property list / picker, with unit counts per property (`units.available`). |
| `inventory.get_property(name)` | Property detail screen (amenities, documents, unit stats). |
| `inventory.get_units(property?, project?, availability?, unit_type?, facing?, min_price?, max_price?, min_area?, max_area?, search?, page?, page_size?, order_by?)` | The unit picker behind every property/unit dropdown in the app. |
| `inventory.available_units(property?, project?, search?, unit_type?, facing?, min_price?, max_price?, min_area?, max_area?, page?, page_size?, order_by?)` | Only what can still be sold — what the opportunity screen offers. |
| `inventory.get_unit(name)` | Unit detail screen: unit, open booking, live opportunities. |
| `inventory.resolve_unit(property_unit)` | Given a unit, everything a form should fill in around it — property, project, price, plan. This is the call that stops a user having to name |
| `inventory.availability(project?, property?)` | Inventory position — the number every review meeting starts with. |

#### `templates` (9)

| Endpoint | What it is for |
|---|---|
| `templates.get_payment_templates()` | Templates screen + payment-plan dropdown details (milestones, used by). |
| `templates.get_payment_template(name)` | Open one payment template (detail screen). |
| `templates.save_payment_template(template_name, milestones, name?)` | Create (no `name`) or replace. `milestones`: `[{"milestone": "Booking", "percentage": 10, "offset_months": 0}, …]` -- percentages must |
| `templates.delete_payment_template(name)` | Delete a payment template. |
| `templates.preview_payment_plan(amount?, template?, property_unit?, booking_date?)` | What the plan would look like for this price, before anybody books -- the schedule a salesperson shows the customer. With only `property_un |
| `templates.get_maintenance_templates(include_disabled?)` | Maintenance / recurring-charge templates list (`include_disabled=1` for admin). |
| `templates.get_maintenance_template(name)` | Open one maintenance template (detail screen). |
| `templates.save_maintenance_template(template_name, schedule?, repeat_every_n_months?, repeat_amount?, repeat_item_code?, disabled?, name?)` | `schedule`: one-off charges, `[{"month_no": 0, "description": "Corpus fund", "amount": 25000, "item_code": null, "fixed_due_date": null}] |
| `templates.apply_templates(units?, property?, payment_plan_template?, maintenance_plan_template?, maintenance_start_date?, only_available?)` | Set the payment plan and/or maintenance template on many units at once: a JSON list of `units`, or every unit of `property`. Pass `""` |

#### `layout` (9)

| Endpoint | What it is for |
|---|---|
| `layout.get_layout(property?, property_unit?)` | The plot layout of a property -- or of the property a unit sits in, with `focus` set to that unit so the screen can zoom to it. |
| `layout.project_layouts(project)` | Every property of a project with its layout state -- for the project screen's Layout tab, so nobody has to search for a property first. Open |
| `layout.save_layout(property, units, world?, annotations?)` | `units`: `[{name, layout_shape: Rect\|Polygon\|Circle, layout_x, layout_y, layout_w, layout_h, layout_rotation, layout_points}]`; `world` |
| `layout.site_map(project?, property?, availability?)` | Pins: properties and their units that have coordinates. |
| `layout.resolve_location(query)` | Coordinates ("12.97, 77.59"), any Google Maps link (maps.app.goo.gl short links too) or a place name -> candidate points. |
| `layout.set_location(doctype, name, latitude?, longitude?, query?)` | Save a point on a Property or Property Unit -- either coordinates, or a `query` resolved the same way as `resolve_location` (first match |
| `layout.editor_assets()` | The layout engine the desk editor and the portal site map run on -- a dependency-free SVG editor (draw rect / polygon / circle, drag, resize |
| `layout.set_unit_shape(property_unit, layout_shape, layout_x?, layout_y?, layout_w?, layout_h?, layout_rotation?, layout_points?)` | Place (or move) one unit on its property's layout -- for a screen that edits a plot at a time instead of saving the whole plan. |
| `layout.clear_unit_shape(property_unit)` | Take a unit off the layout (it stays in inventory). |

#### `projects` (10)

| Endpoint | What it is for |
|---|---|
| `projects.create_project(data?)` | A new development. Everything else -- properties, units, leads -- hangs off it, so it is the first thing set up. |
| `projects.update_project(name, data?)` | Save edits to a project — send only changed fields in `data`. |
| `projects.get_projects(search?, status?, page?, page_size?, order_by?, with_stats?)` | Project list / picker with headline stats (`with_stats=0` for a light picker). |
| `projects.get_project(name)` | Project "Details" tab: project + its properties. |
| `projects.overview(name, from_date?, to_date?)` | Everything about one development, in one request. |
| `projects.project_inventory(name)` | Project "Inventory" tab: units per property. |
| `projects.project_funnel(name, from_date?, to_date?)` | Project "Funnel" tab: leads and opportunities by status. |
| `projects.project_bookings(name, page?, page_size?)` | Bookings under the development, newest first. |
| `projects.project_operations(name)` | Project "Operations" tab: issues and work orders by status. |
| `projects.project_activity(name, limit?)` | The last things that happened on this development, across doctypes — what a manager opens the project to see. |

#### `tasks` (9)

| Endpoint | What it is for |
|---|---|
| `tasks.get_tasks(project?, status?, assigned_to?, mine?, overdue?, parent_task?, search?, filters?, page?, page_size?, order_by?)` | `mine=1` = assigned to me; `assigned_to=user` for someone else; `overdue=1` = past its end date and not done. |
| `tasks.get_task(name)` | Open one task (detail screen). |
| `tasks.create_task(data?, assign_to?)` | `assign_to`: a user, or a JSON list of users. |
| `tasks.update_task(name, data?)` | Save edits to a task — send only changed fields in `data`. |
| `tasks.set_status(name, status, note?)` | Task status buttons (Open / Working / Pending Review / Completed / Cancelled); `note` goes on the timeline. |
| `tasks.assign_task(name, user, note?, keep_others?)` | Give the task to `user` (a user or JSON list). By default the task has one owner and earlier assignees are released; `keep_others=1` add |
| `tasks.unassign_task(name, user)` | Remove one assignee from a task. |
| `tasks.delete_task(name)` | Delete a task. |
| `tasks.options()` | Task dropdowns: statuses, priorities, types (load once). |

#### `billing` (13)

| Endpoint | What it is for |
|---|---|
| `billing.options()` | What a payment screen needs: modes of payment and the sale items an ad-hoc charge can be raised against. |
| `billing.get_invoices(customer?, booking?, property_unit?, status?, overdue?, from_date?, to_date?, search?, page?, page_size?, order_by?)` | Sales Invoices. `booking` = every invoice raised for that deal (its milestones plus anything billed on its unit to its customer, e.g. main |
| `billing.get_invoice(name)` | Open one invoice (detail screen). |
| `billing.get_payments(customer?, booking?, invoice?, from_date?, to_date?, page?, page_size?)` | payment list screen: paged, searchable, filter by the params shown. |
| `billing.get_payment(name)` | Payment detail: what it was allocated against, advance left. |
| `billing.statement(booking)` | Everything money about one booking: plan, invoices, payments, totals -- the customer's ledger for that deal. |
| `billing.generate_invoice(payment_plan)` | Bill one milestone of a booking's payment plan (the desk's "Generate Invoice" button on Payment Plan). |
| `billing.generate_due_invoices(booking, upto_date?)` | Bill every milestone of a booking that is due by `upto_date` (default today) and not invoiced yet. |
| `billing.create_invoice(customer?, items?, booking?, property_unit?, due_date?, submit?, remarks?)` | An ad-hoc charge outside the payment plan. |
| `billing.submit_invoice(name)` | Submit / confirm a invoice. |
| `billing.cancel_invoice(name, reason?)` | Cancel a invoice; `reason` is kept as a comment. |
| `billing.record_payment(amount, mode_of_payment, invoice?, booking?, customer?, posting_date?, reference_no?, reference_date?, remarks?, submit?)` | Money received. Three ways to aim it: |
| `billing.cancel_payment(name, reason?)` | Cancel a payment; `reason` is kept as a comment. |

#### `allocations` (14)

| Endpoint | What it is for |
|---|---|
| `allocations.get_allocations(customer?, property_unit?, booking?, status?, allocation_type?, search?, page?, page_size?)` | allocation list screen: paged, searchable, filter by the params shown. |
| `allocations.get_allocation(name)` | Open one allocation (detail screen). |
| `allocations.create_allocation(data?, submit?)` | New allocation from a form; returns the created record. |
| `allocations.update_allocation(name, data?)` | Save edits to a allocation — send only changed fields in `data`. |
| `allocations.submit_allocation(name)` | Hand the unit over: it becomes Allocated (sale) or Leased. |
| `allocations.cancel_allocation(name, reason?)` | Terminate: the unit goes back to Available. |
| `allocations.renew_lease(name, new_end_date, escalation_percent?)` | "Renew" on a lease / rental allocation: new end date, optional rent escalation %. |
| `allocations.create_from_booking(booking, allocation_type?, start_date?, signed_date?, with_agreement?, submit?, security_deposit_amount?)` | Confirmed booking -> agreement + allocation, in one step. Idempotent: an existing live allocation for the booking is returned as is. |
| `allocations.get_agreements(customer?, property_unit?, status?, agreement_type?, search?, page?, page_size?)` | agreement list screen: paged, searchable, filter by the params shown. |
| `allocations.get_agreement(name)` | Open one agreement (detail screen). |
| `allocations.create_agreement(data?)` | New agreement from a form; returns the created record. |
| `allocations.update_agreement(name, data?)` | Save edits to a agreement — send only changed fields in `data`. |
| `allocations.record_security_deposit(name)` | Book the deposit (Journal Entry to the Security Deposit account in Property Core Settings). |
| `allocations.refund_security_deposit(name)` | "Refund deposit" on an agreement at exit (reversing Journal Entry). |

#### `maintenance` (12)

| Endpoint | What it is for |
|---|---|
| `maintenance.get_tasks(property_unit?, property?, project?, customer?, status?, mine?, assigned_to?, overdue?, from_date?, to_date?, search?, page?, page_size?, order_by?)` | `overdue=1` = date passed and not done; `mine=1` = assigned to me. |
| `maintenance.get_task(name)` | Open one task (detail screen). |
| `maintenance.create_task(data?)` | A visit off the schedule (a repair, a one-off clean-up …). |
| `maintenance.update_task(name, data?)` | Save edits to a task — send only changed fields in `data`. |
| `maintenance.assign(name, user)` | Give a maintenance visit to someone (their desk ToDo + "mine" list). |
| `maintenance.post_update(name, note?, progress?, update_type?, files?, filename?, content?)` | Progress from site. `update_type`: Progress / Blocked / Note. Proof: multipart `file` (repeatable), or `files: [{filename, content}]` |
| `maintenance.complete(name, work_done?, files?, filename?, content?)` | Finish the visit. Proof sent here is attached first, so one call can carry the photos and close the task. |
| `maintenance.cancel(name, reason?)` | Skip a visit (customer away, not needed); `reason` kept. |
| `maintenance.reopen(name, reason?)` | Reopen a completed / cancelled visit. |
| `maintenance.unit_history(property_unit)` | Everything maintenance on one unit: the schedule (charges, billed or to come) and every visit with its updates and proof. |
| `maintenance.generate_now(property_unit?, property?)` | Open whatever visits are due in the lead window now, without waiting for the nightly run -- one unit, or every unit of a property. |
| `maintenance.summary(property?, project?)` | Counts for a maintenance board: open, in progress, overdue, due this week, completed this month. |

#### `files` (7)

| Endpoint | What it is for |
|---|---|
| `files.attach(doctype, name, filename?, content?, fieldname?, is_private?)` | "Upload" on any record's Files tab; `fieldname` also sets an Attach field (layout_image, document_attachment). |
| `files.get_attachments(doctype, name)` | attachment list screen: paged, searchable, filter by the params shown. |
| `files.remove_attachment(name)` | Delete an attachment (the File id from get_attachments). |
| `files.drive_folder(doctype, name, create?)` | The Drive folder of a Property, Property Booking, Property Unit (its booking's) or Project (its first property's tree). `create=1` builds |
| `files.drive_list(doctype, name, folder?)` | Contents of the record's folder, or of `folder` inside it. |
| `files.drive_create_folder(doctype, name, title, parent?)` | "+ Folder" inside a property / booking Drive folder. |
| `files.drive_upload(doctype, name, folder?, filename?, content?)` | Upload into the record's Drive folder (or `folder` inside it). Multipart `file` or base64 `content` + `filename`. |

#### `activity` (6)

| Endpoint | What it is for |
|---|---|
| `activity.add_comment(doctype, name, text)` | Comment box on any record's timeline. |
| `activity.get_comments(doctype, name, limit?)` | comment list screen: paged, searchable, filter by the params shown. |
| `activity.timeline(doctype, name, limit?)` | Comments, assignments, attachments, field changes and communications on the record, newest first. |
| `activity.assign(doctype, name, user, note?)` | One working owner: earlier open assignments are released. |
| `activity.unassign(doctype, name, user)` | Remove an assignee from any record. |
| `activity.my_assignments(status?, reference_type?, page?, page_size?)` | Everything assigned to me (desk ToDo), across records. |

#### `operations` (9)

| Endpoint | What it is for |
|---|---|
| `operations.get_work_orders(property_unit?, status?, assigned_to?, mine?, search?, page?, page_size?)` | work order list screen: paged, searchable, filter by the params shown. |
| `operations.get_work_order(name)` | Open one work order (detail screen). |
| `operations.create_work_order(data?)` | New work order from a form; returns the created record. |
| `operations.update_work_order(name, data?)` | Save edits to a work order — send only changed fields in `data`. |
| `operations.get_issues(customer?, property_unit?, status?, search?, page?, page_size?)` | issue list screen: paged, searchable, filter by the params shown. |
| `operations.get_issue(name)` | Open one issue (detail screen). |
| `operations.create_issue(data?)` | New issue from a form; returns the created record. |
| `operations.update_issue(name, data?)` | Save edits to a issue — send only changed fields in `data`. |
| `operations.options()` | Issue / work-order dropdowns (load once). |
