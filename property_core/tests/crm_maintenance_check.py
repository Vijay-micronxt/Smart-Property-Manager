"""Maintenance visits end to end: a unit's plan opens a task N days before the
date, updates carry photo proof, completion needs proof, the unit / CRM API /
customer portal all show the same trail.

Test site only: it creates records. HTTP part (needs crm*@test.local logins):

    SITE=http://127.0.0.1:8003 HOST=review.site \\
    python property_core/tests/crm_maintenance_check.py

The portal part runs inside the site (it impersonates the buyer):

    bench --site review.site execute property_core.tests.crm_maintenance_check.portal --kwargs "{'task': 'MNT-…'}"
"""
import base64, json, os, sys, time

SITE = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
H = {"Host": os.environ["HOST"]} if os.environ.get("HOST") else {}
P = "/api/method/property_core.api.crm."
TAG = str(int(time.time()) % 100000)
passed, failed = 0, []
PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()


def check(label, cond, detail=""):
    global passed
    if cond:
        passed += 1
        print("  ok  ", label)
    else:
        failed.append(label)
        print("  FAIL", label, str(detail)[:500])


def main():
    import requests

    def session(user):
        s = requests.Session(); s.headers.update(H)
        assert s.post(SITE + "/api/method/login", data={"usr": user, "pwd": "TestPass@123"}).ok
        return s

    def call(s, fn, get=False, upload=None, **args):
        data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in args.items() if v is not None}
        r = s.get(SITE + P + fn, params=data) if get else s.post(SITE + P + fn, data=data, files=upload)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:300]}
        return r.ok and (body.get("message") or {}).get("status") == "ok", body

    def ok(s, fn, **args):
        good, body = call(s, fn, **args)
        check(fn, good, body.get("exception") or body)
        return (body.get("message") or {}).get("data") if good else None

    admin, exe = session("crmadmin@test.local"), session("crmexec1@test.local")
    today = time.strftime("%Y-%m-%d")
    in2 = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))

    print("== setup: plan + two units (due today, due in 2 days)")
    mt = ok(admin, "templates.save_maintenance_template", template_name=f"Visit Plan {TAG}",
            schedule=[{"month_no": 1, "description": "First clean-up", "amount": 2000}], repeat_every_n_months=1, repeat_amount=1000)
    prop = ok(admin, "inventory.create_property", data={"property_name": f"Maint Property {TAG}", "property_type": "Township"})
    units = ok(admin, "inventory.bulk_create_units", property=prop["name"], prefix="M-", count=2,
               defaults={"unit_type": "Plot", "area": 1000, "base_price": 500000})["created"]
    u_now, u_soon = units[0]["name"], units[1]["name"]
    ok(admin, "templates.apply_templates", units=[u_now], maintenance_plan_template=mt["name"], maintenance_start_date=today)
    ok(admin, "templates.apply_templates", units=[u_soon], maintenance_plan_template=mt["name"], maintenance_start_date=in2)
    cust = ok(admin, "customers.create_customer", data={"customer_name": f"Maint Buyer {TAG}", "email_id": f"mbuyer{TAG}@test.local"})

    print("== booking opens the visit (billed today, and 2 days ahead)")
    for unit in (u_now, u_soon):
        ok(admin, "bookings.create_booking", data={"customer": cust["name"], "property_unit": unit, "booking_amount": 50000}, submit=1)
    t_now = ok(admin, "maintenance.get_tasks", get=True, property_unit=u_now)["rows"]
    t_soon = ok(admin, "maintenance.get_tasks", get=True, property_unit=u_soon)["rows"]
    check("task opened for today's visit, tied to its invoice", len(t_now) == 1 and t_now[0]["sales_invoice"], t_now)
    check("task opened 2 days ahead, not billed yet", len(t_soon) == 1 and not t_soon[0]["sales_invoice"]
          and t_soon[0]["scheduled_date"] == in2, t_soon)
    again = ok(admin, "maintenance.generate_now", property_unit=u_now)
    check("re-run opens nothing new", again and again["created"] == [], again)
    task = t_now[0]["name"]

    print("== work on it")
    ok(admin, "maintenance.assign", name=task, user="crmexec1@test.local")
    denied, _ = call(exe, "maintenance.post_update", name=task, note="x")
    check("sales executive cannot post maintenance updates", not denied)
    up = ok(admin, "maintenance.post_update", name=task, note="Weeds cleared on the east side", progress=40,
            files=[{"filename": "east.png", "content": PNG}])
    check("update carries proof", up and len(up["proof"]) == 1 and up["status"] == "In Progress" and up["progress"] == 40, up)
    no_proof = ok(admin, "maintenance.create_task", data={"property_unit": u_now, "subject": "Fix gate hinge"})
    blocked, body = call(admin, "maintenance.complete", name=no_proof["name"], work_done="done")
    check("cannot complete without proof", not blocked and "proof" in json.dumps(body).lower(), body.get("exception"))
    done = ok(admin, "maintenance.complete", name=no_proof["name"], work_done="Hinge replaced",
              upload={"file": ("gate.png", base64.b64decode(PNG), "image/png")})
    check("multipart proof + complete in one call", done and done["status"] == "Completed" and done["proof_count"] == 1, done)
    fin = ok(admin, "maintenance.complete", name=task, work_done="Clean-up finished")
    check("complete with earlier proof", fin and fin["status"] == "Completed" and fin["progress"] == 100, fin)
    note, _ = call(admin, "maintenance.post_update", name=task, note="late", progress=10)
    check("no progress after completion", not note)

    print("== read back")
    t = ok(admin, "maintenance.get_task", get=True, name=task)
    check("task has updates + proof", t and len(t["updates"]) == 1 and t["proof_count"] == 1 and t["completed_by"], t and t.get("updates"))
    h = ok(admin, "maintenance.unit_history", get=True, property_unit=u_now)
    check("unit history: schedule + 2 tasks, both done", h and len(h["tasks"]) == 2 and h["summary"]["completed"] == 2 and h["schedule"], h and h["summary"])
    s = ok(admin, "maintenance.summary", get=True, property=prop["name"])
    check("summary counts", s and s["completed_this_month"] == 2 and s["open"] == 1, s)
    ex = ok(exe, "maintenance.get_tasks", get=True, property_unit=u_now)
    check("executive can read the trail", ex and ex["total"] == 2, ex)
    ok(admin, "maintenance.cancel", name=t_soon[0]["name"], reason="customer away")
    ok(admin, "maintenance.reopen", name=t_soon[0]["name"])

    print(f"\n{passed} passed, {len(failed)} failed  (portal check: task={task} unit={u_now})")
    return task


def portal(task):
    """Customer side, inside the site: the buyer sees their visits and can
    open the proof; someone else's buyer cannot."""
    import frappe
    from property_core.api.portal import maintenance as pm

    unit, customer = frappe.db.get_value("Property Maintenance Task", task, ["property_unit", "customer"])
    user = frappe.db.get_value("Portal User", {"parent": customer, "parenttype": "Customer"}, "user")
    check("buyer has a portal login", bool(user), customer)
    frappe.set_user(user)
    rows = pm.tasks()["data"]["tasks"]
    check("portal lists the visits", any(r["name"] == task for r in rows), rows)
    one = pm.task(task)["data"]
    proof = [p for u in one["updates"] for p in u["proof"]]
    check("portal task shows update + proof link", proof and proof[0]["download_url"], one)
    frappe.local.response = frappe._dict()
    pm.proof(proof[0]["name"])
    check("proof streams", frappe.local.response.filecontent[:4] == b"\x89PNG", frappe.local.response.get("filename"))

    other = frappe.get_all("Portal User", filters={"parenttype": "Customer", "parent": ["!=", customer]}, pluck="user", limit=1)
    if other:
        frappe.set_user(other[0])
        try:
            pm.proof(proof[0]["name"])
            check("other customer refused", False)
        except Exception:
            check("other customer refused", True)
    frappe.set_user("Administrator")
    print(f"portal: {passed} passed, {len(failed)} failed")
    return {"passed": passed, "failed": failed}


if __name__ == "__main__":
    main()
    sys.exit(1 if failed else 0)
