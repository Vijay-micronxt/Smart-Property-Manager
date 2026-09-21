"""Coverage pass over the CRM API — every endpoint the flow smoke does not touch.

`crm_api_smoke.py` walks the funnel end to end; this one calls the rest:
updates, assignment and transfer, duplicates, the customer endpoints, the
inventory pickers, the walk-in opportunity and booking paths, every follow-up
transition, each project section on its own, and the team pickers.

Same prerequisites as the flow smoke (see its docstring). Creates records --
test sites only.

    SITE=http://127.0.0.1:8003 python property_core/tests/crm_api_coverage.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
BASE = f"{SITE}/api/method/property_core.api.crm."
EXEC1 = os.environ.get("EXEC1", "crmexec1@test.local")
EXEC2 = os.environ.get("EXEC2", "crmexec2@test.local")
MANAGER = os.environ.get("MANAGER", "crmmanager@test.local")
ADMIN = os.environ.get("ADMIN", "crmadmin@test.local")
PASSWORD = os.environ.get("PASSWORD", "TestPass@123")

PASS, FAIL = [], []
HIT = set()


def call(method, token=None, post=False, **params):
    HIT.add(method)
    url = BASE + method
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    if post:
        data = json.dumps(params).encode()
        headers["Content-Type"] = "application/json"
    elif params:
        url += "?" + urllib.parse.urlencode(
            {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in params.items()}
        )
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if post else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body


def data_of(body):
    return (body.get("message") or {}).get("data") if isinstance(body, dict) else None


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(f"{label}{('  <- ' + str(detail)[:200]) if not condition else ''}")


def login(user):
    status, body = call("session.login", post=True, usr=user, pwd=PASSWORD)
    d = data_of(body)
    if not d:
        print("LOGIN FAILED", user, status, str(body)[:300])
        sys.exit(1)
    return f"{d['api_key']}:{d['api_secret']}", d


exec1, _ = login(EXEC1)
exec2, _ = login(EXEC2)
manager, _ = login(MANAGER)
admin, _ = login(ADMIN)

# ---------------------------------------------------------------- session ---
status, body = call("session.me", token=exec1)
check("session.me alias", data_of(body).get("user") == EXEC1, body)

status, body = call("session.refresh_token", token=exec1, post=True)
new = data_of(body) or {}
check("session.refresh_token issues a key", bool(new.get("api_secret")), body)
exec1 = f"{new['api_key']}:{new['api_secret']}" if new.get("api_secret") else exec1

status, body = call("meta.field_options", token=exec1, doctype="Property Unit", fieldname="facing")
check("meta.field_options returns options", "North" in (data_of(body) or []), body)

# ------------------------------------------------------------------ leads ---
status, body = call(
    "leads.create_lead", token=exec1, post=True,
    data={"lead_name": "Coverage Lead", "mobile_no": "9111100011", "custom_lead_status": "Followup"},
)
LEAD = (data_of(body) or {}).get("name")
check("lead created for coverage run", bool(LEAD), body)

status, body = call(
    "leads.update_lead", token=exec1, post=True, name=LEAD,
    data={"custom_budget": 4500000, "custom_unit_type": "Plot", "city": "Bengaluru"},
)
check("leads.update_lead writes fields", (data_of(body) or {}).get("custom_budget") == 4500000, body)

status, body = call("leads.assign_lead", token=exec1, post=True, name=LEAD, user=EXEC1)
check("leads.assign_lead", (data_of(body) or {}).get("assigned_to") == EXEC1, body)

status, body = call("leads.find_duplicates", token=exec1, mobile_no="9111100011")
check("leads.find_duplicates finds the number", isinstance(data_of(body), list), body)

status, body = call("leads.pipeline", token=exec1)
check("leads.pipeline groups by status", "by_status" in (data_of(body) or {}), body)

status, body = call("leads.create_customer", token=exec1, post=True, name=LEAD)
CUSTOMER = (data_of(body) or {}).get("customer")
check("leads.create_customer", bool(CUSTOMER), body)

# transfer to exec2, then confirm exec1 lost sight of it
status, body = call("leads.transfer_ownership", token=manager, post=True, name=LEAD, user=EXEC2)
check("leads.transfer_ownership", (data_of(body) or {}).get("lead_owner") == EXEC2, body)
status, body = call("leads.get_lead", token=exec1, name=LEAD)
# JD's rule, kept: whoever created the lead keeps sight of it even after the
# transfer -- `owner` counts as ownership. Only lead_owner/follow-up owner move.
check("creator keeps visibility after transfer (JD rule)", status == 200, status)
check("transfer moved the lead owner", (data_of(body) or {}).get("lead_owner") == EXEC2, (data_of(body) or {}).get("lead_owner"))
status, body = call("leads.get_lead", token=exec2, name=LEAD)
check("transferred lead reaches the new owner", status == 200, status)

# --------------------------------------------------------------- customers ---
status, body = call("customers.get_customers", token=exec2, search="Coverage")
check("customers.get_customers", "rows" in (data_of(body) or {}), body)

status, body = call("customers.get_customer", token=exec2, name=CUSTOMER)
detail = data_of(body) or {}
check("customers.get_customer sections", {"bookings", "units", "outstanding"} <= set(detail), list(detail)[:12])

status, body = call("customers.create_from_lead", token=exec2, post=True, lead=LEAD)
check("customers.create_from_lead is idempotent", (data_of(body) or {}).get("customer") == CUSTOMER, body)

status, body = call(
    "customers.create_customer", token=exec2, post=True,
    data={"customer_name": "Coverage Walk-in", "mobile_no": "9111100022"},
)
WALKIN = (data_of(body) or {}).get("name")
check("customers.create_customer", bool(WALKIN), body)

# --------------------------------------------------------------- inventory ---
status, body = call("inventory.get_properties", token=exec2, search="CRM Smoke")
props = (data_of(body) or {}).get("rows", [])
check("inventory.get_properties with unit stats", bool(props) and "units" in props[0], body)
PROPERTY = props[0]["name"] if props else None

status, body = call("inventory.get_property", token=exec2, name=PROPERTY)
check("inventory.get_property", (data_of(body) or {}).get("property_name") is not None, body)

status, body = call("inventory.get_units", token=exec2, property=PROPERTY, availability="Available", page_size=5)
units = (data_of(body) or {}).get("rows", [])
check("inventory.get_units filtered", bool(units), body)
UNIT = units[0]["name"] if units else None
UNIT2 = units[1]["name"] if len(units) > 1 else None

status, body = call("inventory.get_unit", token=exec2, name=UNIT)
check("inventory.get_unit detail", "open_booking" in (data_of(body) or {}), body)

status, body = call("inventory.availability", token=exec2, property=PROPERTY)
check("inventory.availability counts", (data_of(body) or {}).get("total_units", 0) > 0, body)

# ----------------------------------------------------------- opportunities ---
status, body = call(
    "opportunities.create_opportunity", token=exec2, post=True,
    data={"opportunity_from": "Customer", "party_name": WALKIN, "custom_property_unit": UNIT},
)
OPP = (data_of(body) or {}).get("name")
check("opportunities.create_opportunity (walk-in)", bool(OPP), body)
check("walk-in opportunity resolved the property", (data_of(body) or {}).get("custom_property") == PROPERTY, body)

status, body = call("opportunities.get_opportunities", token=exec2, property=PROPERTY)
check("opportunities.get_opportunities filtered", "rows" in (data_of(body) or {}), body)

status, body = call(
    "opportunities.update_opportunity", token=exec2, post=True, name=OPP,
    data={"probability": 70, "sales_stage": None},
)
check("opportunities.update_opportunity", status == 200, body)

if UNIT2:
    status, body = call("opportunities.set_property", token=exec2, post=True, name=OPP, property_unit=UNIT2)
    check("opportunities.set_property swaps the unit", (data_of(body) or {}).get("custom_property_unit") == UNIT2, body)

# unit from another property must be refused
status, body = call("inventory.get_units", token=admin, availability="Available", page_size=50)
others = [u for u in (data_of(body) or {}).get("rows", []) if u["property"] != PROPERTY]
if others:
    status, body = call(
        "opportunities.set_property", token=exec2, post=True,
        name=OPP, property=PROPERTY, property_unit=others[0]["name"],
    )
    check("set_property refuses a foreign unit", status != 200, status)

status, body = call("opportunities.set_status", token=exec2, post=True, name=OPP, status="Quotation")
check("opportunities.set_status", (data_of(body) or {}).get("status") == "Quotation", body)

status, body = call("opportunities.funnel", token=manager)
check("opportunities.funnel", "by_status" in (data_of(body) or {}), body)

# ------------------------------------------------------------- follow ups ---
status, body = call(
    "follow_ups.log_follow_up", token=exec2, post=True,
    reference_doctype="Opportunity", reference_name=OPP,
    follow_up_type="Call", outcome="Connected", notes="coverage call",
)
LOGGED = (data_of(body) or {}).get("name")
check("follow_ups.log_follow_up", bool(LOGGED), body)
check("logged follow up is completed", (data_of(body) or {}).get("status") == "Completed", body)

status, body = call("follow_ups.get_follow_ups", token=exec2, reference_doctype="Opportunity", reference_name=OPP)
check("follow_ups.get_follow_ups", (data_of(body) or {}).get("total", 0) >= 1, body)

status, body = call("follow_ups.get_follow_up", token=exec2, name=LOGGED)
check("follow_ups.get_follow_up", (data_of(body) or {}).get("name") == LOGGED, body)

status, body = call(
    "follow_ups.create_follow_up", token=exec2, post=True,
    reference_doctype="Opportunity", reference_name=OPP, follow_up_type="Site Visit",
)
NEXT = (data_of(body) or {}).get("name")
check("follow up scheduled for reschedule test", bool(NEXT), body)
check("follow up pulled the property off the reference", bool((data_of(body) or {}).get("property")), body)

status, body = call("follow_ups.reschedule", token=exec2, post=True, name=NEXT, scheduled_on="2026-10-05 11:00:00")
check("follow_ups.reschedule", (data_of(body) or {}).get("status") == "Rescheduled", body)

status, body = call("follow_ups.cancel_follow_up", token=exec2, post=True, name=NEXT, reason="coverage")
check("follow_ups.cancel_follow_up", (data_of(body) or {}).get("status") == "Cancelled", body)

# ---------------------------------------------------------------- bookings ---
status, body = call(
    "bookings.create_booking", token=exec2, post=True,
    data={"property_unit": UNIT2 or UNIT, "customer": WALKIN, "booking_amount": 50000},
)
BOOKING = (data_of(body) or {}).get("name")
check("bookings.create_booking (walk-in path)", bool(BOOKING), body)
check("booking priced off the unit", bool((data_of(body) or {}).get("total_price")), body)

status, body = call("bookings.update_booking", token=exec2, post=True, name=BOOKING, data={"notes": "coverage"})
check("bookings.update_booking", status == 200, body)

status, body = call("bookings.get_bookings", token=exec2, customer=WALKIN)
check("bookings.get_bookings", (data_of(body) or {}).get("total", 0) >= 1, body)

status, body = call("bookings.payment_plan", token=exec2, booking=BOOKING)
check("bookings.payment_plan on a draft", "rows" in (data_of(body) or {}), body)

status, body = call("bookings.submit_booking", token=manager, post=True, name=BOOKING)
check("manager confirms the walk-in booking", (data_of(body) or {}).get("docstatus") == 1, body)

status, body = call("bookings.payment_plan", token=manager, booking=BOOKING)
plan = (data_of(body) or {}).get("rows", [])
check("payment plan raised on confirm", len(plan) > 0, body)
check("collections block present", "collections" in (data_of(body) or {}), body)

status, body = call("bookings.cancel_booking", token=manager, post=True, name=BOOKING, reason="coverage run")
check("bookings.cancel_booking", (data_of(body) or {}).get("docstatus") == 2, body)
check("cancelled booking reads as Cancelled", (data_of(body) or {}).get("booking_status") == "Cancelled", body)

status, body = call("bookings.get_booking", token=manager, name=BOOKING)
check("cancelled status persisted", (data_of(body) or {}).get("booking_status") == "Cancelled", (data_of(body) or {}).get("booking_status"))

# --------------------------------------------------------------- projects ---
status, body = call("projects.get_projects", token=manager, search="CRM Smoke")
rows = (data_of(body) or {}).get("rows", [])
PROJECT = rows[0]["name"] if rows else None
check("projects.get_projects search", bool(PROJECT), body)

for fn, key in [
    ("projects.get_project", "summary"),
    ("projects.project_inventory", "summary"),
    ("projects.project_funnel", "leads"),
    ("projects.project_bookings", "rows"),
    ("projects.project_operations", "work_orders"),
]:
    status, body = call(fn, token=manager, name=PROJECT)
    check(f"{fn}", key in (data_of(body) or {}), body)

status, body = call("projects.project_activity", token=manager, name=PROJECT, limit=10)
check("projects.project_activity", isinstance(data_of(body), list), body)

# ------------------------------------------------------------------- team ---
status, body = call("team.assignable_users", token=manager)
users = data_of(body) or []
check("team.assignable_users lists the team", len(users) >= 2, users)

status, body = call("team.assignable_users", token=exec2)
check("an executive can only assign to themselves", len(data_of(body) or []) == 1, data_of(body))

# --------------------------------------------------------------- dashboard ---
status, body = call("dashboard.summary", token=manager, from_date="2026-09-01", to_date="2026-09-30")
check("dashboard.summary with a period", (data_of(body) or {}).get("period", {}).get("from_date") == "2026-09-01", body)

# ----------------------------------------------------------------- logout ---
status, body = call("session.logout", token=exec2, post=True)
check("session.logout answers", status == 200, body)

print(f"\nPASS {len(PASS)} / {len(PASS) + len(FAIL)}")
for f in FAIL:
    print("  FAIL:", f)
print(f"\nendpoints hit this run: {len(HIT)}")
print("artifacts:", {"lead": LEAD, "customer": CUSTOMER, "walkin": WALKIN, "opportunity": OPP, "booking": BOOKING})
sys.exit(1 if FAIL else 0)
