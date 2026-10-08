"""End-to-end check of the CRM "whole backend" endpoints: dashboards, project
tasks, templates, bulk units, layout/map, invoices + payments, allocation,
attachments, Drive, activity, operations -- as an admin and an executive.

Test site only: it creates records. Needs the crm*@test.local logins
(password TestPass@123) and a personal Drive Team for crmadmin.

    SITE=http://127.0.0.1:8003 HOST=review.site     python property_core/tests/crm_backend_check.py
"""
import base64, json, os, sys, time
import requests

SITE = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
H = {"Host": os.environ["HOST"]} if os.environ.get("HOST") else {}
P = "/api/method/property_core.api.crm."
TAG = str(int(time.time()) % 100000)
passed, failed = 0, []


def session(user):
    s = requests.Session()
    s.headers.update(H)
    r = s.post(SITE + "/api/method/login", data={"usr": user, "pwd": "TestPass@123"})
    assert r.ok, r.text
    return s


def call(s, fn, method="POST", files=None, expect_ok=True, **args):
    data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in args.items() if v is not None}
    if method == "GET":
        r = s.get(SITE + P + fn, params=data)
    else:
        r = s.post(SITE + P + fn, data=data, files=files)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    good = r.ok and body.get("message", {}).get("status") == "ok"
    return good, r.status_code, body


def check(label, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("  ok  ", label)
    else:
        failed.append(label)
        print("  FAIL", label, str(detail)[:600])


def ok(s, fn, **args):
    good, code, body = call(s, fn, **args)
    check(fn, good, (code, body.get("exception") or body.get("_server_messages") or body))
    return (body.get("message") or {}).get("data") if good else None


admin = session("crmadmin@test.local")
exe = session("crmexec1@test.local")

print("== dashboards")
d = ok(admin, "dashboard.lead_dashboard", method="GET", view_type="organisation")
check("lead_dashboard shape", d and {"total_leads", "pending_leads", "status_counts", "source_counts", "team_members", "user_type"} <= set(d))
f = ok(admin, "dashboard.flow", method="GET", view_type="organisation", date_range="all")
check("flow sections", f and all(k in f for k in ("leads", "opportunities", "bookings", "allocations", "money", "inventory", "stages")))
ok(admin, "dashboard.trend", method="GET", view_type="team", months=4)
e = ok(exe, "dashboard.flow", method="GET", view_type="my")
check("exec flow sees own only", e and e["user_type"] == "regular")
e2 = ok(exe, "dashboard.lead_dashboard", method="GET", view_type="organisation")
check("exec organisation = empty", e2 and e2["total_leads"] == 0)
ok(admin, "dashboard.lead_dashboard", method="GET", view_type="my", date_range="custom", date_from="2026-01-01", date_to="2026-12-31")

print("== project + tasks")
proj = ok(admin, "projects.create_project", data={"project_name": f"API Project {TAG}", "expected_start_date": "2026-10-01"})
pname = proj and proj["name"]
ok(admin, "projects.update_project", name=pname, data={"notes": "phase 1"})
t = ok(admin, "tasks.create_task", data={"subject": f"Get layout approval {TAG}", "project": pname, "exp_end_date": "2026-10-15"},
       assign_to="crmexec1@test.local")
tname = t and t["name"]
check("task assigned", t and [a["user"] for a in t["assigned_to"]] == ["crmexec1@test.local"], t)
mine = ok(exe, "tasks.get_tasks", method="GET", mine=1)
check("exec sees task in mine", mine and any(r["name"] == tname for r in mine["rows"]))
ok(exe, "tasks.set_status", name=tname, status="Working", note="started")
ok(admin, "tasks.assign_task", name=tname, user="crmexec2@test.local")
tt = ok(admin, "tasks.get_task", method="GET", name=tname)
check("reassigned to one owner", tt and tt["assigned_to"] == ["crmexec2@test.local"], tt and tt["assigned_to"])
ok(admin, "tasks.options", method="GET")

print("== inventory + templates")
prop = ok(admin, "inventory.create_property", data={"property_name": f"API Property {TAG}", "property_type": "Township", "project": pname})
prop_name = prop and prop["name"]
ok(admin, "inventory.update_property", name=prop_name, data={"amenities": [{"amenity_name": "Clubhouse", "amenity_type": "Recreation"}]})
tpl = ok(admin, "templates.save_payment_template", template_name=f"API Plan {TAG}",
         milestones=[{"milestone": "Booking", "percentage": 20, "offset_months": 0}, {"milestone": "Registration", "percentage": 80, "offset_months": 1}])
bad, _, _ = call(admin, "templates.save_payment_template", template_name=f"Bad {TAG}", milestones=[{"milestone": "x", "percentage": 50, "offset_months": 0}])
check("template must total 100", not bad)
mt = ok(admin, "templates.save_maintenance_template", template_name=f"API Maint {TAG}",
        schedule=[{"month_no": 1, "description": "Corpus", "amount": 10000}], repeat_every_n_months=1, repeat_amount=1500)
units = ok(admin, "inventory.bulk_create_units", property=prop_name, prefix="A-", start=1, count=3,
           defaults={"unit_type": "Plot", "area": 1200, "base_price": 1000000})
check("3 units", units and len(units["created"]) == 3, units)
again = ok(admin, "inventory.bulk_create_units", property=prop_name, prefix="A-", start=1, count=3, defaults={"unit_type": "Plot"})
check("rerun skips", again and len(again["skipped"]) == 3)
unit = units["created"][0]["name"]
ok(admin, "templates.apply_templates", property=prop_name, payment_plan_template=tpl["name"], maintenance_plan_template=mt["name"])
ok(admin, "templates.preview_payment_plan", method="GET", amount=None, property_unit=unit)
ok(admin, "templates.get_payment_templates", method="GET")
ok(admin, "templates.get_maintenance_templates", method="GET")
ok(admin, "inventory.update_unit", name=unit, data={"base_price": 1100000, "facing": None})
ok(admin, "inventory.set_unit_status", name=units["created"][2]["name"], status="Maintenance Blocked", reason="drain work")
denied, code, _ = call(exe, "inventory.update_unit", name=unit, data={"base_price": 1})
check("exec cannot edit unit", not denied)

print("== layout / map")
ok(admin, "layout.get_layout", method="GET", property=prop_name)
ok(admin, "layout.save_layout", property=prop_name, units=[{"name": unit, "layout_shape": "Rect", "layout_x": 10, "layout_y": 10, "layout_w": 50, "layout_h": 30}])
loc = ok(admin, "layout.set_location", doctype="Property Unit", name=unit, latitude=12.9716, longitude=77.5946)
check("location saved", loc and abs(loc["latitude"] - 12.9716) < 1e-4, loc)
sm = ok(admin, "layout.site_map", method="GET", project=pname)
check("site map pin", sm and any(u["name"] == unit for u in sm["units"]))
ok(admin, "layout.resolve_location", method="GET", query="12.97, 77.59")

print("== booking -> invoice -> payment -> allocation")
cust = ok(admin, "customers.create_customer", data={"customer_name": f"API Buyer {TAG}", "mobile_no": "98" + TAG.zfill(8)})
bk = ok(admin, "bookings.create_booking", data={"customer": cust["name"], "property_unit": unit, "booking_amount": 100000}, submit=1)
bname = bk and bk["name"]
plan = ok(admin, "bookings.payment_plan", method="GET", booking=bname)
# booking amount first, then the template's milestones reduced by it, adding up to the agreement value
total_price = bk and bk.get("total_price")
check("plan starts with the booking amount", plan and plan["rows"][0]["amount"] == 100000, plan)
check("plan adds up to the agreement value",
      plan and abs(sum(r["amount"] for r in plan["rows"]) - (total_price or 0)) < 0.01, plan and total_price)
inv = ok(admin, "billing.generate_invoice", payment_plan=plan["rows"][0]["name"])
check("invoice submitted", inv and inv["docstatus"] == 1, inv)
due = ok(admin, "billing.generate_due_invoices", booking=bname, upto_date="2027-12-31")
extra = ok(admin, "billing.create_invoice", booking=bname, items=[{"rate": 50000, "description": "Corner premium"}])
opts = ok(admin, "billing.options", method="GET")
mop = next((m["name"] for m in opts["modes_of_payment"] if m["type"] == "Cash"), None) if opts else None
pay = ok(admin, "billing.record_payment", booking=bname, amount=300000, mode_of_payment=mop)
check("payment spread over open invoices", pay and abs(sum(a["amount"] for a in pay["allocated"]) + pay["advance"] - 300000) < 0.01
      and inv["invoice"] in [a["invoice"] for a in pay["allocated"]], pay)
st = ok(admin, "billing.statement", method="GET", booking=bname)
check("statement has payments", st and len(st["payments"]) >= 1 and st["outstanding"] < st["billed"], st and {k: st[k] for k in ("billed", "outstanding")})
ok(admin, "billing.get_invoices", method="GET", booking=bname)
ok(admin, "billing.get_payments", method="GET", booking=bname)
ok(admin, "billing.get_invoice", method="GET", name=inv["invoice"])
denied, _, _ = call(exe, "billing.record_payment", invoice=inv["invoice"], amount=1, mode_of_payment=mop)
check("exec cannot record payment", not denied)
al = ok(admin, "allocations.create_from_booking", booking=bname, signed_date="2026-09-29")
check("allocated + agreement", al and al["docstatus"] == 1 and al["agreement"], al)
ustat = ok(admin, "inventory.get_unit", method="GET", name=unit)
check("unit Allocated", ustat and ustat["availability_status"] == "Allocated", ustat and ustat["availability_status"])
ok(admin, "allocations.get_allocations", method="GET", booking=bname)
ok(admin, "allocations.get_agreement", method="GET", name=al["agreement"])
ok(admin, "allocations.update_agreement", name=al["agreement"], data={"agreement_status": "Active"})

print("== files + drive + activity")
pdf = base64.b64encode(b"signed agreement scan").decode()
att = ok(admin, "files.attach", doctype="Property Agreement", name=al["agreement"], filename="agreement.txt", content=pdf, fieldname="document_attachment")
lst = ok(admin, "files.get_attachments", method="GET", doctype="Property Agreement", name=al["agreement"])
check("attachment listed", lst and any(r["name"] == att["name"] for r in lst))
mp = ok(admin, "files.attach", doctype="Property Booking", name=bname, files={"file": ("id.txt", b"aadhaar copy")})
ok(admin, "files.remove_attachment", name=mp["name"])
dfold = ok(admin, "files.drive_folder", doctype="Property Booking", name=bname)
if dfold and dfold.get("folder"):
    ok(admin, "files.drive_create_folder", doctype="Property Booking", name=bname, title="KYC")
    up = ok(admin, "files.drive_upload", doctype="Property Booking", name=bname, filename="kyc.txt", content=base64.b64encode(b"kyc").decode())
    dl = ok(admin, "files.drive_list", method="GET", doctype="Property Booking", name=bname)
    check("drive lists upload + folder", dl and {"KYC", "kyc.txt"} <= {i["title"] for i in dl["items"]}, dl and [i["title"] for i in dl["items"]])
    pf = ok(admin, "files.drive_folder", doctype="Property", name=prop_name)
    outside, _, _ = call(admin, "files.drive_list", method="GET", doctype="Property Booking", name=bname, folder=pf and pf["folder"])
    check("folder outside record refused", not outside)
else:
    check("drive folder", False, dfold)
ok(admin, "activity.add_comment", doctype="Property Booking", name=bname, text="Customer wants east gate")
ok(admin, "activity.assign", doctype="Property Booking", name=bname, user="crmexec1@test.local")
tl = ok(admin, "activity.timeline", method="GET", doctype="Property Booking", name=bname)
check("timeline has comment", tl and any(e["type"] == "Comment" for e in tl))
ok(exe, "activity.my_assignments", method="GET")

print("== operations")
wo = ok(admin, "operations.create_work_order", data={"property_unit": unit, "work_type": "Maintenance", "description": "fix gate"})
ok(admin, "operations.update_work_order", name=wo["name"], data={"status": "In Progress", "progress": 30})
iss = ok(admin, "operations.create_issue", data={"subject": f"Water leak {TAG}", "customer": cust["name"], "property_unit": unit})
ok(admin, "operations.get_issues", method="GET", property_unit=unit)
ok(admin, "operations.options", method="GET")

print("== cancel paths")
ok(admin, "allocations.cancel_allocation", name=al["name"], reason="test")
a2 = ok(admin, "allocations.get_allocation", method="GET", name=al["name"])
check("cancelled allocation reads Terminated", a2 and a2["status"] == "Terminated", a2 and a2["status"])
ok(admin, "billing.cancel_payment", name=pay["name"])
ok(admin, "billing.cancel_invoice", name=extra["name"])
ws = ok(admin, "session.whoami", method="GET")
check("whoami lists Sales Invoice perms", ws and "Sales Invoice" in ws["permissions"])

print(f"\n{passed} passed, {len(failed)} failed")
for f in failed:
    print("  -", f)
sys.exit(1 if failed else 0)
