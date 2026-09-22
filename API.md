# API reference — every endpoint in Smart Property Manager

154 whitelisted endpoints across three surfaces:

| Surface | For | Count | Detail |
|---|---|---|---|
| **Staff CRM API** — `property_core.api.crm.*` | the sales app: enquiry → booking | 64 | [CRM_API.md](CRM_API.md) |
| **Customer portal API** — `property_core.api.portal.*` + `api.auth.*` | buyers and tenants | 36 | [CUSTOMER_PORTAL_API.md](CUSTOMER_PORTAL_API.md) |
| **Feature and integration endpoints** | the desk forms, payment gateways, notifications | 54 | this file, sections 5–8 |

This file is the index: what exists, where it lives, who may call it. The two
linked documents carry request/response detail for the surfaces an outside app
talks to.

---

## 1. Calling convention

```
https://<site>/api/method/<dotted.python.path>
```

Frappe wraps every reply in `message`. The CRM and portal APIs put their own
envelope inside it:

```json
{"message": {"status": "ok", "message": "Lead CRM-LEAD-2026-00010 created", "data": {...}}}
```

So the payload is `response.message.data`. The older feature endpoints
(sections 5–8) return their value directly in `message` — they were built for
the desk, not for an app.

**Auth.** Two ways in, both accepted everywhere:

* token — `Authorization: token <api_key>:<api_secret>`, issued by
  `property_core.api.crm.session.login` (staff) or `property_core.api.auth.login`
  (customers);
* an ordinary Frappe session cookie, which is what the desk uses.

A call without a token or cookie answers *"Login to access — Function … is not
whitelisted"*. That means **not logged in**, not that the endpoint is missing;
a missing endpoint answers *"No module named …"* instead.

`frappe.auth.get_logged_user` works once logged in but returns only the user
id — use `crm.session.whoami` (staff) or `api.auth.get_logged_in_user`
(customer), which return the profile as well.

**Errors** are HTTP 4xx/5xx carrying Frappe's body: read `exc_type`
(`ValidationError`, `PermissionError`, `AuthenticationError`,
`DoesNotExistError`, `MandatoryError`) and show
`_server_messages[0].message`.

**Guest endpoints** — callable without a login — are only these seven, and
five of them are payment-gateway webhooks:

| Endpoint | Why it is open |
|---|---|
| `api.auth.login` | customer login |
| `api.auth.forgot_password`, `api.auth.reset_password` | OTP reset, before there is a session |
| `crm.session.login` | staff login |
| `...ecommerce.razorpay_webhooks.handle_razorpay_webhook` | gateway callback, signature-verified |
| `...ecommerce.mswipe_webhooks.handle_mswipe_callback` | gateway callback |
| `...paytm_payment_webhook.handle_link_payment`, `...paytm_payment_link.generate_payment_link` | gateway callback and link |

---

## 2. Who sees what

Row-level visibility is enforced by the server, not by the caller, on **Lead,
Opportunity, Property Booking and Property Follow Up**:

| Scope | Role | Sees |
|---|---|---|
| `all` | Property Manager (or System Manager / Administrator) | the whole company |
| `team` | **Property Sales Manager** | own records plus everyone below them in `Employee.reports_to`, at any depth |
| `own` | **Property Sales Executive** (or Sales User) | only what they own or were assigned |

Customers hold none of those roles: the portal API resolves the customer from
the session and scopes every query to their own units.

The two sales roles and the permissions they need are created on migrate.
**Assigning a role to a person is still manual** — Frappe never does that by
itself.

---

## 3. Staff CRM API — `property_core.api.crm.*` (64)

Full detail, payloads and the end-to-end flow: **[CRM_API.md](CRM_API.md)**.

| Module | Endpoints |
|---|---|
| `session` (5) | `login` · `whoami` · `me` · `refresh_token` · `logout` |
| `meta` (2) | `options` · `field_options` |
| `leads` (11) | `get_leads` · `get_lead` · `create_lead` · `update_lead` · `set_status` · `assign_lead` · `transfer_ownership` · `convert_to_opportunity` · `create_customer` · `find_duplicates` · `pipeline` |
| `follow_ups` (8) | `get_follow_ups` · `get_follow_up` · `create_follow_up` · `log_follow_up` · `complete_follow_up` · `reschedule` · `cancel_follow_up` · `my_agenda` |
| `opportunities` (8) | `get_opportunities` · `get_opportunity` · `create_opportunity` · `update_opportunity` · `set_property` · `set_status` · `convert_to_booking` · `funnel` |
| `customers` (4) | `get_customers` · `get_customer` · `create_customer` · `create_from_lead` |
| `inventory` (7) | `get_properties` · `get_property` · `get_units` · `available_units` · `get_unit` · `resolve_unit` · `availability` |
| `bookings` (7) | `get_bookings` · `get_booking` · `create_booking` · `update_booking` · `submit_booking` · `cancel_booking` · `payment_plan` |
| `projects` (8) | `get_projects` · `get_project` · `overview` · `project_inventory` · `project_funnel` · `project_bookings` · `project_operations` · `project_activity` |
| `team` (3) | `my_team` · `assignable_users` · `performance` |
| `dashboard` (1) | `summary` |

Three things worth knowing before writing a client:

* **Derivation is server-side.** A unit implies its property, a property
  implies its project, an opportunity implies its customer (created from the
  lead if nobody did it yet) and its price. Send the unit; do not send the rest.
* **Conversions are idempotent.** `convert_to_opportunity`,
  `convert_to_booking` and `create_from_lead` return what already exists
  instead of making a second one.
* **A booking is created as a draft.** Confirming it is a separate call and a
  separate permission, because confirming reserves the unit, raises the
  payment plan, provisions the buyer's portal login and starts maintenance
  billing.

---

## 4. Customer portal API — `property_core.api.portal.*` (29) and `api.auth.*` (7)

Full detail: **[CUSTOMER_PORTAL_API.md](CUSTOMER_PORTAL_API.md)**.

| Module | Endpoints |
|---|---|
| `api.auth` | `login` · `get_token` · `logout` · `get_logged_in_user` · `change_password` · `forgot_password` · `reset_password` |
| `portal.meta` | `settings` |
| `portal.profile` | `me` · `update_contact` |
| `portal.dashboard` | `summary` |
| `portal.properties` | `my_units` · `unit` · `projects` · `site_map` · `available_units` |
| `portal.bookings` | `list_bookings` · `booking_details` · `book_unit` |
| `portal.billing` | `charges` · `maintenance_charges` · `utility_bills` · `rent_history` · `outstanding_dues` · `payments` · `invoice` · `payment_schedule` |
| `portal.maintenance` | `work_history` · `schedule` · `inspections` · `work_updates` |
| `portal.support` | `issues` · `issue` · `raise_issue` · `add_comment` |
| `portal.documents` | `list_documents` |

`property_core.property_core.api.customer_portal.*` (11 endpoints) is the
older surface the bundled `/customer-portal` page still calls. It stays for
that page; new clients use `api.portal.*`.

---

## 5. Sales and funnel helpers

Called by the desk forms; usable by any client.

| Endpoint | Arguments | Does |
|---|---|---|
| `...crm.opportunity_events.resolve_unit` | `property_unit` | property, project, price, plan and availability for a unit — what the form auto-fills |
| `...crm.customer_from_lead.make_customer_from_lead` | `lead` | Lead → Customer keeping the address (ERPNext's own conversion drops it) |
| `...crm.lead_events.find_duplicates` | `mobile_no`, `exclude` | leads already holding that number |
| `...doctype.property_follow_up.property_follow_up.get_follow_up_history` | `reference_doctype`, `reference_name`, `start`, `page_length` | paged trail for the Follow Ups tab |
| `...property_follow_up.log_follow_up` | `reference_doctype`, `reference_name`, `follow_up_type`, `outcome`, `notes`, `next_follow_up_on`, `next_action`, `scheduled_on`, `assigned_to`, `status` | one-call "log a call" |
| `...property_follow_up.get_open_follow_up` | `reference_doctype`, `reference_name` | the next open touch, if any |
| `...doctype.property_booking.property_booking.make_from_opportunity` | `source_name` | mapped Property Booking off an Opportunity |
| `...property_booking.make_from_property_unit` | `source_name` | the walk-in path: book a unit directly |
| `...crm.whatsapp.templates` / `render_template` / `send` | see [CRM_API.md](CRM_API.md) | message templates, server-rendered preview, send |
| `...crm.telephony.click_to_call` | `to_number`, `reference_doctype`, `reference_name` | dial through the configured provider |

---

## 6. Inventory, map and layout

| Endpoint | Arguments | Does |
|---|---|---|
| `...property_core.geo.resolve` | `query` | a place name, a pasted coordinate pair, or a Google Maps link (short `maps.app.goo.gl` included — the server follows the redirect) → marker candidates. Only allow-listed hosts are ever fetched |
| `...property_core.api.layout.get_layout` | `property` | the plot-layout canvas: units, shapes, world size, annotations |
| `...api.layout.save_layout` | `property`, `units`, `world`, `annotations` | writes the layout back |
| `...utils.drive_folders.create_folders_for_property` | `property_name` | builds the property's Drive folder tree |

`latitude`, `longitude` and `map_link` are kept on Property and Property Unit
whenever the map moves, so lists, reports and the portal never need to open a
map.

---

## 7. Money and operations

| Endpoint | Arguments | Does |
|---|---|---|
| `...doctype.payment_plan.payment_plan.generate_invoice` | `payment_plan_name` | raise the invoice for one milestone |
| `...property_agreement.record_security_deposit` / `refund_security_deposit` | `agreement_name` | deposit in, deposit out |
| `...property_allocation.renew_lease` | `allocation_name`, `new_end_date`, `escalation_percent` | renew with escalation |
| `...property_operations...utility_bill.generate_invoice` | `utility_bill_name` | bill a meter reading |
| `...property_operations.utils.maintenance_schedule.unit_schedule` | `property_unit`, `months_ahead` | what maintenance is due, and when |
| `...maintenance_schedule.bill_now` | `property_unit` | raise everything already due |
| `...work_order_update.post_update` / `updates` | `work_order`, `progress`, `note`, `update_type` | site progress trail |
| `...inspection_checklist.get_default_items` | — | the standard checklist rows |
| `...commission_settlement.get_pending_entries` | `sales_person` | unsettled commission for a person |

Notifications (WhatsApp/email) each expose a "send it now" so nobody waits for
the nightly job: `notifications.invoice.send_now`,
`notifications.payment_reminders.send_reminder_now`,
`notifications.receipts.send_receipt_now` and `reconcile_now`,
`notifications.lead_followup.send_follow_up_now`,
`notifications.dispatcher.resend_log`,
`doctype.property_notification_log.retry`.

---

## 8. Payments

| Endpoint | Guest | Does |
|---|---|---|
| `...ecommerce.razorpay_integration.order_payment` | no | start a Razorpay order |
| `...razorpay_integration.verify_payment_signature` | no | verify the signature |
| `...razorpay_integration.capture_payment` | no | capture and record |
| `...ecommerce.razorpay_webhooks.handle_razorpay_webhook` | yes | gateway callback |
| `...ecommerce.mswipe_integration.order_payment` | no | start an Mswipe order |
| `...ecommerce.mswipe_webhooks.handle_mswipe_callback` | yes | gateway callback |
| `...api.paytm_payment_link.generate_ecommerce_payment_link` | no | Paytm link for a Sales Order |
| `...paytm_payment_link.generate_payment_link` | yes | Paytm link, public entry |
| `...paytm_payment_webhook.handle_link_payment` | yes | Paytm callback |

All three gateways resolve a **Property Booking** to its next unpaid
instalment and a **Payment Plan** to its invoice, so "pay now" works against a
booking, not only against a Sales Order.

Details and setup: [PAYMENT_INTEGRATION.md](PAYMENT_INTEGRATION.md).

---

## 9. Deploying this

```bash
bench --site <site> migrate            # required
bench build --app property_core        # required — JavaScript changed
bench --site <site> clear-cache        # required
bench restart                          # or: sudo supervisorctl restart all
```

`migrate` is what creates the two sales roles, grants their permissions,
adds the new Opportunity fields (`custom_project`,
`custom_next_follow_up_date`) and runs the patches. Nothing else has to be
run by hand.

**After migrate, one manual step:** give each person their role — Property
Manager, Property Sales Manager or Property Sales Executive — and make sure
their Employee record has `user_id` set and `reports_to` pointing at their
manager. That reporting chain is what decides who sees whose pipeline; an
Employee with no `user_id` gets no team.

Roles can be assigned from the desk, or:

```bash
bench --site <site> execute property_core.property_core.setup.roles.assign_role \
      --kwargs "{'user': 'hema@jdfarmlands.com', 'role': 'Property Sales Executive'}"
```

---

## 10. Tests

| Suite | Assertions | Proves |
|---|---|---|
| `property_core/tests/crm_api_smoke.py` | 38 | the funnel end to end over HTTP |
| `property_core/tests/crm_api_coverage.py` | 59 | every remaining endpoint |
| `property_core/tests/crm_data_verify.py` | 51 | what actually reached the database |
| `property_core/tests/geo_resolve_check.py` | 7 | every kind of map input, and the internal-URL refusal |

```bash
SITE=http://127.0.0.1:8003 python property_core/tests/crm_api_smoke.py
SITE=http://127.0.0.1:8003 python property_core/tests/crm_api_coverage.py
bench --site <site> execute property_core.tests.crm_data_verify.run
bench --site <site> execute property_core.tests.geo_resolve_check.run
```

The first three need three test logins (an executive, a second executive and
their manager) tied together through `Employee.reports_to`, and a property
with a free unit. Each suite's docstring says exactly what it expects. They
create records: test sites only.
