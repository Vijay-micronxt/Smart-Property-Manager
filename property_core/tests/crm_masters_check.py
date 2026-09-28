"""Dropdown masters, end to end over HTTP.

Lead status, lead source, follow-up type/outcome, unit type, facing and
property type are Link fields onto masters. This proves, through the API only:

* ``meta.options`` still answers every key the app reads, as lists of strings,
  and now also ``status_details``, ``sales_persons`` and ``masters``;
* a value an admin adds to a master shows up in ``meta.options`` and can be
  saved on a record straight away -- no code change, no deploy;
* a disabled value leaves the dropdowns but old records keep it;
* a status flagged "hide from sales" drops out of an executive's lead list,
  and its ERPNext status mapping comes from the master;
* a value that is not in the master is refused;
* ``inventory.create_property`` / ``create_unit`` work for an admin and are
  refused for an executive.

Run against a test site (it creates records):

    SITE=http://127.0.0.1:8003 python property_core/tests/crm_masters_check.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SITE = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
PASSWORD = os.environ.get("PASSWORD", "TestPass@123")
ADMIN = "crmadmin@test.local"
EXEC = "crmexec1@test.local"

RESULTS = []
TAG = str(int(time.time()) % 100000)


def http(method, path, token=None, params=None, body=None):
    url = SITE + path
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
        )
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"token {token}"
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def api(method, fn, token, **kw):
    path = "/api/method/property_core.api.crm." + fn
    if method == "GET":
        return http("GET", path, token, params=kw)
    return http("POST", path, token, body=kw)


def data(resp):
    return (resp[1].get("message") or {}).get("data") if isinstance(resp[1].get("message"), dict) else None


def resource(method, doctype, token, body=None, name=None):
    path = "/api/resource/" + urllib.parse.quote(doctype) + ("/" + urllib.parse.quote(name) if name else "")
    return http(method, path, token, body=body)


def check(label, ok, detail=""):
    ok = bool(ok)
    RESULTS.append(ok)
    print(("  ok   " if ok else "  FAIL ") + label + ("" if ok else f"  -> {detail}"))


def login(user):
    status, body = http("POST", "/api/method/property_core.api.crm.session.login", body={"usr": user, "pwd": PASSWORD})
    d = body["message"]["data"]
    return f"{d['api_key']}:{d['api_secret']}"


def main():
    admin = login(ADMIN)
    exec1 = login(EXEC)

    print("meta.options keeps its shape")
    meta = data(api("GET", "meta.options", admin))
    old_keys = {
        "lead": ["statuses", "working_statuses", "dead_statuses", "sources", "unit_types", "facings"],
        "opportunity": ["statuses", "types", "sources", "stages"],
        "follow_up": ["types", "statuses", "outcomes", "reference_doctypes"],
        "booking": ["statuses", "payment_plan_templates"],
        "unit": ["types", "availability", "facings"],
        "property": ["types", "statuses"],
    }
    for section, keys in old_keys.items():
        for key in keys:
            value = meta.get(section, {}).get(key)
            check(
                f"{section}.{key} is a list of strings",
                isinstance(value, list) and all(isinstance(v, str) for v in value),
                value,
            )
    check("company + currency still there", isinstance(meta.get("company"), list) and meta.get("currency"))
    check("lead.statuses non-empty", len(meta["lead"]["statuses"]) > 0)
    check("new: lead.status_details", isinstance(meta["lead"].get("status_details"), list))
    check("new: booking.sales_persons", isinstance(meta["booking"].get("sales_persons"), list))
    check("new: masters map", meta.get("masters", {}).get("lead.statuses") == "Property Lead Status")
    defaults = meta.get("defaults") or {}
    check("new: defaults from the doctypes", defaults.get("unit.availability") == "Available" and defaults.get("follow_up.types") == "Call", defaults)
    check("every default is one of its own options", all(
        v in meta[k.split(".")[0]][k.split(".")[1]] for k, v in defaults.items() if "." in k and k.split(".")[0] in meta and isinstance(meta[k.split(".")[0]].get(k.split(".")[1]), list)
    ), defaults)
    exec_meta = data(api("GET", "meta.options", exec1))
    check(
        "executive gets the same dropdowns",
        exec_meta["lead"]["statuses"] == meta["lead"]["statuses"]
        and exec_meta["booking"]["payment_plan_templates"] == meta["booking"]["payment_plan_templates"],
    )
    fo = data(api("GET", "meta.field_options", admin, doctype="Property Unit", fieldname="unit_type"))
    check("field_options on a Link field answers the master's values", fo == meta["unit"]["types"], fo)

    print("an admin adds values, the API offers them at once")
    status_name = f"Hot {TAG}"
    source_name = f"Insta Reel {TAG}"
    outcome_name = f"Asked Brochure {TAG}"
    unit_type = f"Farm Villa {TAG}"
    ptype = f"Resort {TAG}"
    r = resource("POST", "Property Lead Status", admin, {"status_name": status_name, "erpnext_status": "Interested", "indicator": "purple"})
    check("create Property Lead Status", r[0] == 200, r[1])
    r = resource("POST", "Lead Source", admin, {"source_name": source_name})
    check("create Lead Source", r[0] == 200, r[1])
    r = resource("POST", "Property Follow Up Outcome", admin, {"outcome_name": outcome_name})
    check("create Property Follow Up Outcome", r[0] == 200, r[1])
    r = resource("POST", "Property Unit Type", admin, {"unit_type": unit_type})
    check("create Property Unit Type", r[0] == 200, r[1])
    r = resource("POST", "Property Type", admin, {"property_type": ptype})
    check("create Property Type", r[0] == 200, r[1])
    r = resource("POST", "Property Type", exec1, {"property_type": f"Exec {TAG}"})
    check("executive may not add to a master", r[0] == 403, r[0])

    meta = data(api("GET", "meta.options", admin))
    check("new status offered", status_name in meta["lead"]["statuses"])
    check("new source offered", source_name in meta["lead"]["sources"])
    check("new outcome offered", outcome_name in meta["follow_up"]["outcomes"])
    check("new unit type offered", unit_type in meta["unit"]["types"])
    check("new property type offered", ptype in meta["property"]["types"])
    details = {d["status"]: d for d in meta["lead"]["status_details"]}
    check("status_details carries the master's rules", details.get(status_name, {}).get("erpnext_status") == "Interested")

    print("inventory create endpoints")
    r = api("POST", "inventory.create_property", admin, data={"property_name": f"Masters Prop {TAG}", "property_type": ptype})
    prop = data(r)
    check("admin creates a property with a new type", r[0] == 200 and prop and prop["property_type"] == ptype, r[1])
    r = api(
        "POST",
        "inventory.create_unit",
        admin,
        data={"property": prop["name"], "unit_number": f"M-{TAG}", "unit_type": unit_type, "area": 1500, "base_price": 1800000, "facing": "North"},
    )
    unit = data(r)
    check("admin creates a unit with a new unit type", r[0] == 200 and unit and unit["unit_type"] == unit_type, r[1])
    check("unit defaults to Available", unit and unit["availability_status"] == "Available")
    r = api("POST", "inventory.create_property", exec1, data={"property_name": f"Exec Prop {TAG}", "property_type": ptype})
    check("executive may not create a property", r[0] == 403, r[0])
    r = api("POST", "inventory.create_unit", admin, data={"property": prop["name"], "unit_number": f"X-{TAG}", "unit_type": "Spaceship"})
    check("unknown unit type refused", r[0] == 417 and "Spaceship" in json.dumps(r[1]), r[0])

    print("leads use the new values")
    r = api(
        "POST",
        "leads.create_lead",
        exec1,
        data={"lead_name": f"Masters Lead {TAG}", "mobile_no": f"97{TAG:0>8}", "custom_lead_status": status_name, "custom_lead_source": source_name, "custom_unit_type": unit_type},
    )
    lead = data(r)
    check("lead created with new status + source + unit type", r[0] == 200 and lead, r[1])
    lead_name = lead["name"]
    got = data(api("GET", "leads.get_lead", exec1, name=lead_name))
    check("ERPNext status mapped from the master (Interested)", got["status"] == "Interested", got.get("status"))
    check("source mirrored to native Lead.source", got.get("source") == source_name, got.get("source"))
    r = api("POST", "leads.create_lead", exec1, data={"lead_name": "Bad", "mobile_no": f"96{TAG:0>8}", "custom_lead_status": "No Such Status"})
    check("unknown lead status refused", r[0] == 417 and "No Such Status" in json.dumps(r[1]), r[0])

    r = api("POST", "follow_ups.log_follow_up", exec1, reference_doctype="Lead", reference_name=lead_name, outcome=outcome_name, notes="brochure")
    check("follow-up logged with the new outcome", r[0] == 200 and data(r)["outcome"] == outcome_name, r[1])

    print("hide from sales, from the master")
    rows = data(api("GET", "leads.get_leads", exec1, search=lead_name))["rows"]
    check("executive sees the lead before", any(x["name"] == lead_name for x in rows))
    r = resource("PUT", "Property Lead Status", admin, {"hide_from_sales": 1}, name=status_name)
    check("admin flags the status hidden", r[0] == 200, r[1])
    rows = data(api("GET", "leads.get_leads", exec1, search=lead_name))["rows"]
    check("executive no longer sees it", not any(x["name"] == lead_name for x in rows))
    rows = data(api("GET", "leads.get_leads", admin, search=lead_name))["rows"]
    check("admin still sees it", any(x["name"] == lead_name for x in rows))
    meta = data(api("GET", "meta.options", admin))
    check("status now in dead_statuses", status_name in meta["lead"]["dead_statuses"])

    print("disable a value")
    r = resource("PUT", "Property Follow Up Outcome", admin, {"enabled": 0}, name=outcome_name)
    check("admin disables the outcome", r[0] == 200, r[1])
    meta = data(api("GET", "meta.options", admin))
    check("disabled outcome gone from dropdown", outcome_name not in meta["follow_up"]["outcomes"])
    fu = data(api("GET", "follow_ups.get_follow_ups", admin, reference_doctype="Lead", reference_name=lead_name))["rows"]
    check("old follow-up keeps the value", any(x["outcome"] == outcome_name for x in fu))

    passed = sum(RESULTS)
    print(f"\nPASS {passed} / {len(RESULTS)}")
    return passed == len(RESULTS)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
