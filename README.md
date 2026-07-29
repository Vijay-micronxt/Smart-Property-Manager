# Smart Property Manager

A Frappe/ERPNext app for end-to-end real estate lifecycle management — from lead to allocation, payment plans, maintenance, and sales commissions. Installs as a single app with three modules.

---

## Modules

| Module | What it covers |
|---|---|
| **Property Core** | Property & Unit inventory, bookings, allocations, payment plans, agreements, CRM integration, customer portal |
| **Property Operations** | Work Orders, Maintenance Plans (recurring billing), Inspection Checklists, Utility Meters & Bills |
| **Property Commissions** | Commission Rules, Commission Entries (auto-created on booking), Commission Settlements |

---

## Key Features

- **Inventory** — Property and Property Unit master records with availability status managed automatically by the allocation engine
- **Lead → Booking → Allocation → Agreement** — full sales pipeline with ERPNext CRM integration (Lead/Opportunity linked to a specific unit from the start)
- **Payment Plans** — milestone-based templates; daily scheduler auto-generates and submits Sales Invoices as milestones fall due
- **Customer Portal** — auto-provisioned portal access on booking; customers view their units, bookings, and raise Issues
- **Issue → Work Order** — customers raise Issues (ERPNext native); staff create linked Work Orders for physical dispatch; Work Order completion auto-resolves the Issue
- **Recurring Maintenance Billing** — Maintenance Plan Template with month-wise charges and optional repeat cycle; daily scheduler bills each unit automatically, never double-bills
- **Inspections & Utilities** — periodic inspection checklists, utility meter readings, and utility bills
- **Commissions** — rule-driven commission entries auto-created on booking submit, settled via Commission Settlement linked to a payment entry
- **Notifications via Server Script** — no notification code in the app; every automated event is a standard Frappe doc event, wired to WhatsApp/SMS/email through Server Scripts independently of app releases

---

## Requirements

- [Frappe Framework](https://frappeframework.com) v14 or v15
- [ERPNext](https://erpnext.com) v14 or v15
- Python 3.10+

---

## Installation

### 1. Get the app

```bash
bench get-app https://github.com/Vijay-micronxt/Smart-Property-Manager
```

### 2. Install on your site

```bash
bench --site <your-site-name> install-app property_core
```

### 3. Run migrations

```bash
bench --site <your-site-name> migrate
```

### 4. (Optional) Set the Maintenance Item Code

Go to **Property Core Settings** and set **Maintenance Item Code** — this is the ERPNext Item used when auto-generating recurring maintenance invoices. Required before the maintenance billing scheduler will run.

---

## Post-install Configuration

| Setting | Where | Purpose |
|---|---|---|
| Maintenance Item Code | Property Core Settings | Default ERPNext Item for maintenance invoices |
| Payment Plan Template | Property / Property Booking | Milestone schedule for auto-invoicing |
| Commission Rule | Commission Rule doctype | Agent commission rate per booking |

---

## Daily Schedulers

Three background jobs run automatically once the app is installed:

| Job | What it does |
|---|---|
| `billing_engine` | Raises rent/lease invoices for active allocations |
| `payment_plan_billing` | Raises Sales Invoices for due payment plan milestones |
| `maintenance_billing` | Raises Sales Invoices for due recurring maintenance charges |

No manual trigger is needed — all three are idempotent (safe to re-run, never double-bill).

---

## Roles

| Role | Typical access |
|---|---|
| Property Manager | Full access across all modules |
| Sales User | Leads, Bookings, Allocations, Commissions |
| Operations User | Issues, Work Orders, Maintenance Plans, Inspections, Utilities |
| Finance User | Invoicing, Utility Bills |
| Commission Manager | Commission Rules, Entries, Settlements |
| Property Owner | Read-only Inspections and Issues |
| Tenant / Customer | Own bookings, own Issues, own utility bills (via portal) |

---

## Documentation

| Document | Contents |
|---|---|
| [FEATURES.md](FEATURES.md) | Full field-by-field reference for every DocType |
| [HOW_TO_USE.md](HOW_TO_USE.md) | Day-to-day workflow walkthrough |
| [PAYMENT_INTEGRATION.md](PAYMENT_INTEGRATION.md) | Razorpay / mSwipe / Paytm Pay-by-Link — endpoint reference and curl examples |
| [USE_CASES.md](USE_CASES.md) | End-user scenarios |
| [TEST_CASES.md](TEST_CASES.md) | Step-by-step QA test scripts |

---

## Repository Structure

```
Smart-Property-Manager/
├── setup.py                        # pip entry-point — bench get-app reads this
├── requirements.txt
├── MANIFEST.in
└── property_core/                  # Single Frappe app (app_name = "property_core")
    ├── hooks.py                    # Merged hooks for all three modules
    ├── modules.txt
    ├── property_core/              # Module 1 — core lifecycle
    │   ├── doctype/                # 12 DocTypes (Property, Unit, Booking, ...)
    │   ├── utils/                  # Billing engines, allocation, availability
    │   ├── api/                    # Customer portal whitelisted APIs
    │   ├── customer_kyc.py         # 14 KYC custom fields on Customer
    │   └── crm_links.py            # Custom fields on Lead / Opportunity
    ├── property_operations/        # Module 2 — ops & maintenance
    │   ├── doctype/                # 7 DocTypes (Work Order, Maintenance Plan, ...)
    │   ├── utils/maintenance_billing.py
    │   ├── issue_links.py          # Custom field: Issue → Work Order
    │   └── property_unit_links.py  # Custom fields: maintenance on Property Unit
    ├── property_commissions/       # Module 3 — commissions
    │   └── doctype/                # 4 DocTypes (Rule, Entry, Settlement, ...)
    └── public/js/                  # 15 client-side JS files (one per DocType)
```

---

## License

MIT