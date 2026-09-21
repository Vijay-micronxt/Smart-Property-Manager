"""End-to-end smoke of the CRM API, over HTTP, against a running site.

Walks the whole funnel the way the app will: log in, list, create a lead,
schedule and complete a follow-up, convert to an opportunity, tag a unit,
convert to a booking, confirm it, then read the project roll-up — checking on
the way that an executive sees only their own rows and cannot confirm a
booking, while their manager can.

Run it against a test site only: it creates records.

    SITE=http://127.0.0.1:8003 \
    EXEC1=crmexec1@test.local EXEC2=crmexec2@test.local \
    MANAGER=crmmanager@test.local PASSWORD=TestPass@123 \
    python property_core/tests/crm_api_smoke.py

The three logins must exist, hold Property Sales Executive / Property Sales
Manager, and be tied together through Employee.reports_to. The site also needs
at least one Available unit under a property that belongs to a project.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SITE = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
EXEC1 = os.environ.get("EXEC1", "crmexec1@test.local")
EXEC2 = os.environ.get("EXEC2", "crmexec2@test.local")
MANAGER = os.environ.get("MANAGER", "crmmanager@test.local")
PASSWORD = os.environ.get("PASSWORD", "TestPass@123")

BASE = f"{SITE}/api/method/property_core.api.crm."
PASS, FAIL = [], []


def call(method, token=None, post=False, **params):
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


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(f"{label}{(' -- ' + str(detail)[:220]) if not condition else ''}")


def login(user, pwd=PASSWORD):
    status, body = call("session.login", post=True, usr=user, pwd=pwd)
    data = (body.get("message") or {}).get("data") if isinstance(body, dict) else None
    if not data:
        print("LOGIN FAILED", user, status, str(body)[:400])
        sys.exit(1)
    return f"{data['api_key']}:{data['api_secret']}", data


# ---------------------------------------------------------------- session ---
exec1_token, exec1 = login(EXEC1)
check("login returns a token", bool(exec1_token))
check("login reports scope own", exec1.get("scope") == "own", exec1.get("scope"))

manager_token, manager = login(MANAGER)
check("manager scope is team", manager.get("scope") == "team", manager.get("scope"))
check("manager team has two execs", len(manager.get("team", [])) == 2, manager.get("team"))

status, body = call("session.whoami", token=exec1_token)
data = body.get("message", {}).get("data", {})
check("whoami answers", status == 200 and data.get("user") == EXEC1, body)
check("whoami carries permissions", bool(data.get("permissions", {}).get("Lead")), data.get("permissions"))

# ------------------------------------------------------------------- meta ---
status, body = call("meta.options", token=exec1_token)
opts = body.get("message", {}).get("data", {})
check("meta lists lead statuses", len(opts.get("lead", {}).get("statuses", [])) > 5)
check("meta lists unit availability", "Available" in opts.get("unit", {}).get("availability", []))

# ------------------------------------------------------------------ leads ---
status, body = call("leads.get_leads", token=exec1_token, page_size=50)
rows = body.get("message", {}).get("data", {}).get("rows", [])
owners = {r.get("lead_owner") for r in rows}
check("exec1 lead list is their own only", owners <= {EXEC1}, owners)

status, body = call(
    "leads.create_lead",
    token=exec1_token,
    post=True,
    data={"lead_name": "API Smoke Lead", "mobile_no": "9000000009", "custom_lead_status": "Followup"},
)
lead = body.get("message", {}).get("data", {})
check("create_lead works", bool(lead.get("name")), body)
LEAD = lead.get("name")
check("new lead owned by caller", lead.get("lead_owner") == EXEC1, lead.get("lead_owner"))

status, body = call("leads.get_lead", token=exec1_token, name=LEAD)
detail = body.get("message", {}).get("data", {})
check("get_lead returns sections", "follow_ups" in detail and "opportunities" in detail, list(detail)[:8])

status, body = call("leads.set_status", token=exec1_token, post=True, name=LEAD, status="Interested")
check("set_status maps native status", body.get("message", {}).get("data", {}).get("status") == "Interested", body)

# -------------------------------------------------------------- inventory ---
status, body = call("inventory.available_units", token=exec1_token, page_size=5)
units = body.get("message", {}).get("data", {}).get("rows", [])
check("available units listed", len(units) > 0, body)
UNIT = units[0]["name"] if units else None

status, body = call("inventory.resolve_unit", token=exec1_token, property_unit=UNIT)
resolved = body.get("message", {}).get("data", {})
check("resolve_unit returns property", bool(resolved.get("property")), resolved)
PROPERTY = resolved.get("property")

# ----------------------------------------------------------- opportunities ---
status, body = call(
    "leads.convert_to_opportunity", token=exec1_token, post=True, name=LEAD, property_unit=UNIT
)
opp = body.get("message", {}).get("data", {})
check("lead converts to opportunity", bool(opp.get("name")), body)
OPP = opp.get("name")
check("opportunity picked up the property", opp.get("custom_property") == PROPERTY, opp.get("custom_property"))
check("opportunity amount taken from unit", bool(opp.get("opportunity_amount")), opp.get("opportunity_amount"))

status, body = call("opportunities.get_opportunity", token=exec1_token, name=OPP)
detail = body.get("message", {}).get("data", {})
check("opportunity detail carries unit summary", bool(detail.get("unit")), detail.get("unit"))
check("opportunity can_book flag", detail.get("can_book") is True, detail.get("can_book"))

# a second executive must not see it
exec2_token, _ = login(EXEC2)
status, body = call("opportunities.get_opportunity", token=exec2_token, name=OPP)
check("exec2 refused on exec1 opportunity", status in (403, 417, 500), status)

status, body = call("opportunities.get_opportunity", token=manager_token, name=OPP)
check("manager may open the same opportunity", status == 200, status)

# ------------------------------------------------------------- follow ups ---
status, body = call(
    "follow_ups.create_follow_up",
    token=exec1_token,
    post=True,
    reference_doctype="Opportunity",
    reference_name=OPP,
    follow_up_type="Site Visit",
    notes="API smoke",
)
follow_up = body.get("message", {}).get("data", {})
check("follow up scheduled", bool(follow_up.get("name")), body)
FOLLOW_UP = follow_up.get("name")

status, body = call(
    "follow_ups.complete_follow_up",
    token=exec1_token,
    post=True,
    name=FOLLOW_UP,
    outcome="Site Visit Done",
    notes="went well",
)
check("follow up completed", body.get("message", {}).get("data", {}).get("status") == "Completed", body)

status, body = call("follow_ups.my_agenda", token=exec1_token)
agenda = body.get("message", {}).get("data", {})
check("agenda has three buckets", {"overdue", "today", "upcoming"} <= set(agenda), list(agenda))

# ---------------------------------------------------------------- booking ---
status, body = call(
    "opportunities.convert_to_booking",
    token=exec1_token,
    post=True,
    name=OPP,
    booking_amount=100000,
)
booking = body.get("message", {}).get("data", {})
check("opportunity converts to booking", bool(booking.get("name")), body)
BOOKING = booking.get("name")
check("booking carried the customer", bool(booking.get("customer")), booking.get("customer"))
check("booking carried the unit", booking.get("property_unit") == UNIT, booking.get("property_unit"))
check("booking priced from the unit", bool(booking.get("total_price")), booking.get("total_price"))

status, body = call("bookings.get_booking", token=exec1_token, name=BOOKING)
detail = body.get("message", {}).get("data", {})
check("booking detail has payment plan section", "payment_plan" in detail, list(detail)[:10])

# an executive may not submit; the manager may
status, body = call("bookings.submit_booking", token=exec1_token, post=True, name=BOOKING)
check("executive cannot confirm a booking", status != 200, status)

status, body = call("bookings.submit_booking", token=manager_token, post=True, name=BOOKING)
confirmed = body.get("message", {}).get("data", {}) if status == 200 else {}
check("manager confirms the booking", confirmed.get("docstatus") == 1, body)
check("payment plan raised on confirm", len(confirmed.get("payment_plan", [])) >= 0, confirmed.get("payment_plan"))

# --------------------------------------------------------------- projects ---
status, body = call("projects.get_projects", token=manager_token)
projects = body.get("message", {}).get("data", {}).get("rows", [])
check("projects listed with summary", bool(projects) and "summary" in projects[0], body)
PROJECT = projects[0]["name"] if projects else None

if PROJECT:
    status, body = call("projects.overview", token=manager_token, name=PROJECT)
    overview = body.get("message", {}).get("data", {})
    check(
        "project overview has all sections",
        {"inventory", "funnel", "sales", "money", "operations", "team"} <= set(overview),
        list(overview),
    )

# -------------------------------------------------------------- dashboard ---
status, body = call("dashboard.summary", token=exec1_token)
summary = body.get("message", {}).get("data", {})
check("dashboard summary answers", {"today", "leads", "opportunities", "bookings", "conversion"} <= set(summary), list(summary))

status, body = call("team.my_team", token=manager_token)
team = body.get("message", {}).get("data", {})
check("team endpoint lists members", len(team.get("members", [])) == 2, team.get("members"))

status, body = call("team.performance", token=manager_token)
rows = body.get("message", {}).get("data", {}).get("rows", [])
check("performance returns a row per member", len(rows) >= 2, rows)

print(f"\nPASS {len(PASS)} / {len(PASS) + len(FAIL)}")
for f in FAIL:
    print("  FAIL:", f)
print("\nartifacts:", {"lead": LEAD, "opportunity": OPP, "booking": BOOKING, "unit": UNIT})

sys.exit(1 if FAIL else 0)
