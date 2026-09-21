"""Drive the CRM API over HTTP, then check what it actually wrote.

The other two suites assert what the API says it did. This one distrusts that
and reads the records back out of the database: does a customer made from a
lead really carry the address and the contact, does the opportunity carry the
property, project, amount and phone number, does a confirmed booking really
reserve the unit, raise a payment plan that adds up, and give the buyer a
portal login -- and does cancelling really put the unit back.

Run it inside a site, with the web server up (it calls itself over HTTP):

    bench --site review.site execute property_core.tests.crm_data_verify.run

Needs the same test logins as crm_api_smoke.py, plus a property called
"CRM Smoke Property" with a free unit and the "Luxury Villa Split" payment
plan template on site. Creates records -- test sites only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

import os

import frappe
from frappe.utils import flt

SITE_URL = os.environ.get("SITE", "http://127.0.0.1:8003").rstrip("/")
BASE = f"{SITE_URL}/api/method/property_core.api.crm."
PASSWORD = os.environ.get("PASSWORD", "TestPass@123")
EXEC1 = os.environ.get("EXEC1", "crmexec1@test.local")
MANAGER = os.environ.get("MANAGER", "crmmanager@test.local")
PROPERTY = os.environ.get("PROPERTY", "CRM Smoke Property")
TEMPLATE = os.environ.get("TEMPLATE", "Luxury Villa Split")

PASS, FAIL = [], []

# each run gets its own person, so a rerun never trips the email/mobile
# uniqueness the first run created
import time

TAG = str(int(time.time()))[-6:]
BUYER = f"Deep Verify Buyer {TAG}"
MOBILE = f"93333{TAG[-5:]}"
EMAIL = f"deep.verify.{TAG}@example.com"


def fresh():
    """This script holds its own DB connection while the site writes through
    another one. MariaDB's REPEATABLE READ would otherwise keep showing the
    snapshot from our first read, so end the transaction before every check."""
    frappe.db.rollback()


def check(label, condition, detail=""):
    (PASS if condition else FAIL).append(f"{label}{('  <- ' + str(detail)[:250]) if not condition else ''}")


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
            body = json.loads(resp.read().decode())
            return resp.status, (body.get("message") or {}).get("data")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            raw = json.loads(raw)
        except Exception:
            pass
        return e.code, raw


def login(user):
    status, d = call("session.login", post=True, usr=user, pwd=PASSWORD)
    return f"{d['api_key']}:{d['api_secret']}"


def run():
    PASS.clear()
    FAIL.clear()

    exec1 = login(EXEC1)
    manager = login(MANAGER)

    # fresh unit to work with
    frappe.set_user("Administrator")
    unit = frappe.db.get_value(
        "Property Unit",
        {"property": PROPERTY, "availability_status": "Available"},
        ["name", "base_price", "property"],
        as_dict=True,
    )
    frappe.db.set_value("Property", PROPERTY, "payment_plan_template", TEMPLATE)
    frappe.db.commit()

    # ---------------------------------------------------------------- 1. lead ---
    status, lead = call(
        "leads.create_lead", token=exec1, post=True,
        data={
            "lead_name": BUYER,
            "mobile_no": MOBILE,
            "email_id": EMAIL,
            "custom_lead_status": "Interested",
            "custom_lead_source": "Website",
            "custom_budget": 3000000,
            "custom_unit_type": "Plot",
            "custom_address_line1": "42 MG Road",
            "custom_address_line2": "Indiranagar",
            "city": "Bengaluru",
            "state": "Karnataka",
            "country": "India",
            "custom_pincode": "560038",
        },
    )
    LEAD = (lead or {}).get("name")
    check("lead created over the API", bool(LEAD), lead)
    if not LEAD:
            raise Exception(f"lead creation failed: {lead}")

    fresh()
    row = frappe.db.get_value(
        "Lead", LEAD,
        ["lead_name", "mobile_no", "email_id", "custom_lead_status", "status", "custom_budget",
         "custom_address_line1", "city", "country", "lead_owner", "custom_follow_up_owner"],
        as_dict=True,
    )
    check("lead fields landed in the database", row.mobile_no == MOBILE and row.email_id == EMAIL, row)
    check("native status derived from the CRM status", row.status == "Interested", row.status)
    check("budget stored", flt(row.custom_budget) == 3000000, row.custom_budget)
    check("address line stored on the lead", row.custom_address_line1 == "42 MG Road", row.custom_address_line1)
    check("owner and follow-up owner set to the caller", row.lead_owner == EXEC1 and row.custom_follow_up_owner == EXEC1, row)

    fresh()
    lead_address = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Lead", "link_name": LEAD, "parenttype": "Address"},
        pluck="parent",
    )
    check("an Address record was raised for the lead", bool(lead_address), lead_address)
    if lead_address:
        addr = frappe.get_doc("Address", lead_address[0])
        check("address carries the line, city and pincode",
              addr.address_line1 == "42 MG Road" and addr.city == "Bengaluru" and addr.pincode == "560038",
              {"line": addr.address_line1, "city": addr.city, "pin": addr.pincode})

    # ------------------------------------------------------------ 2. customer ---
    status, out = call("leads.create_customer", token=exec1, post=True, name=LEAD)
    CUSTOMER = (out or {}).get("customer")
    check("customer created from the lead", bool(CUSTOMER), out)

    fresh()
    cust = frappe.db.get_value(
        "Customer", CUSTOMER, ["customer_name", "lead_name", "customer_type", "mobile_no", "email_id"], as_dict=True
    )
    check("customer points back at the lead", cust.lead_name == LEAD, cust)
    check("customer name carried", cust.customer_name == BUYER, cust)

    fresh()
    contacts = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": CUSTOMER, "parenttype": "Contact"},
        pluck="parent",
    )
    check("a Contact is linked to the customer", bool(contacts), contacts)
    if contacts:
        contact = frappe.get_doc("Contact", contacts[0])
        numbers = [p.phone for p in contact.get("phone_nos", [])]
        emails = [e.email_id for e in contact.get("email_ids", [])]
        check("contact carries the mobile number", any(MOBILE in (n or "") for n in numbers), numbers)
        check("contact carries the email", EMAIL in emails, emails)

    fresh()
    cust_address = frappe.get_all(
        "Dynamic Link",
        filters={"link_doctype": "Customer", "link_name": CUSTOMER, "parenttype": "Address"},
        pluck="parent",
    )
    check("the lead's address followed the customer", bool(cust_address), cust_address)

    # calling again must not make a second customer
    status, out2 = call("leads.create_customer", token=exec1, post=True, name=LEAD)
    check("customer creation is idempotent", (out2 or {}).get("customer") == CUSTOMER, out2)
    check("only one customer exists for this lead",
          frappe.db.count("Customer", {"lead_name": LEAD}) == 1, frappe.db.count("Customer", {"lead_name": LEAD}))

    # --------------------------------------------------------- 3. opportunity ---
    status, opp = call(
        "leads.convert_to_opportunity", token=exec1, post=True, name=LEAD, property_unit=unit.name
    )
    OPP = (opp or {}).get("name")
    check("opportunity created from the lead", bool(OPP), opp)

    fresh()
    orow = frappe.db.get_value(
        "Opportunity", OPP,
        ["party_name", "opportunity_from", "custom_property", "custom_property_unit", "custom_project",
         "opportunity_amount", "opportunity_owner", "contact_mobile", "contact_email", "status"],
        as_dict=True,
    )
    check("opportunity points at the lead", orow.party_name == LEAD and orow.opportunity_from == "Lead", orow)
    check("property resolved from the unit", orow.custom_property == unit.property, orow.custom_property)
    check("project stamped from the property",
          orow.custom_project == frappe.db.get_value("Property", unit.property, "project"), orow.custom_project)
    check("amount taken from the unit's price", flt(orow.opportunity_amount) == flt(unit.base_price), orow.opportunity_amount)
    check("contact details carried from the lead", (orow.contact_mobile or "").endswith(MOBILE), orow.contact_mobile)
    check("opportunity owner is the caller", orow.opportunity_owner == EXEC1, orow.opportunity_owner)

    # follow-up with a next date -- the call that crashed on Opportunity
    status, fu = call(
        "follow_ups.log_follow_up", token=exec1, post=True,
        reference_doctype="Opportunity", reference_name=OPP, follow_up_type="Call",
        outcome="Connected", notes="deep verify", next_follow_up_on="2026-10-02 11:00:00",
        next_action="send brochure",
    )
    check("follow up logged on an opportunity", isinstance(fu, dict) and fu.get("name"), fu)
    if isinstance(fu, dict) and fu.get("name"):
        fresh()
        frow = frappe.db.get_value(
            "Property Follow Up", fu["name"],
            ["reference_doctype", "reference_name", "party_name", "contact_number", "property",
             "property_unit", "status", "outcome", "completed_by", "next_follow_up_on"],
            as_dict=True,
        )
        check("follow up pulled party and number off the opportunity",
              frow.party_name and frow.contact_number, frow)
        check("follow up pulled the property and unit", frow.property == unit.property and frow.property_unit == unit.name, frow)
        check("follow up closed as completed", frow.status == "Completed" and frow.completed_by == EXEC1, frow)
        check("next follow-up date pushed onto the opportunity",
              str(frappe.db.get_value("Opportunity", OPP, "custom_next_follow_up_date") or "").startswith("2026-10-02"),
              frappe.db.get_value("Opportunity", OPP, "custom_next_follow_up_date"))

    # ------------------------------------------------------------- 4. booking ---
    status, booking = call(
        "opportunities.convert_to_booking", token=exec1, post=True, name=OPP, booking_amount=150000
    )
    BOOKING = (booking or {}).get("name")
    check("booking raised from the opportunity", bool(BOOKING), booking)

    fresh()
    brow = frappe.db.get_value(
        "Property Booking", BOOKING,
        ["customer", "property_unit", "unit_property", "total_price", "booking_amount", "booking_status",
         "docstatus", "opportunity", "lead", "unit_type", "unit_area", "project"],
        as_dict=True,
    )
    check("booking carries the customer from the lead", brow.customer == CUSTOMER, brow.customer)
    check("booking carries unit and property", brow.property_unit == unit.name and brow.unit_property == unit.property, brow)
    check("agreement value taken from the unit", flt(brow.total_price) == flt(unit.base_price), brow.total_price)
    check("booking links back to the opportunity and lead", brow.opportunity == OPP and brow.lead == LEAD, brow)
    check("booking starts as a draft", brow.docstatus == 0, brow.docstatus)
    check("unit not blocked by a draft booking",
          frappe.db.get_value("Property Unit", unit.name, "availability_status") == "Available",
          frappe.db.get_value("Property Unit", unit.name, "availability_status"))

    # an executive must not be able to confirm
    status, refused = call("bookings.submit_booking", token=exec1, post=True, name=BOOKING)
    check("executive cannot confirm", status != 200, status)

    status, confirmed = call("bookings.submit_booking", token=manager, post=True, name=BOOKING)
    check("manager confirms", (confirmed or {}).get("docstatus") == 1, confirmed)

    fresh()
    brow = frappe.db.get_value(
        "Property Booking", BOOKING, ["docstatus", "booking_status", "customer"], as_dict=True
    )
    check("booking confirmed in the database", brow.docstatus == 1 and brow.booking_status == "Confirmed", brow)
    check("unit reserved on confirm",
          frappe.db.get_value("Property Unit", unit.name, "availability_status") in ("Reserved", "Booked"),
          frappe.db.get_value("Property Unit", unit.name, "availability_status"))
    check("unit stamped with the customer",
          frappe.db.get_value("Property Unit", unit.name, "customer") == CUSTOMER,
          frappe.db.get_value("Property Unit", unit.name, "customer"))
    check("opportunity closed as converted",
          frappe.db.get_value("Opportunity", OPP, "status") == "Converted",
          frappe.db.get_value("Opportunity", OPP, "status"))

    fresh()
    plan = frappe.get_all(
        "Payment Plan", filters={"booking": BOOKING},
        fields=["name", "milestone", "amount", "due_date", "payment_status"], order_by="due_date asc",
    )
    check("payment plan generated", len(plan) == 4, [p.milestone for p in plan])
    check("plan adds up to the agreement value",
          abs(sum(flt(p.amount) for p in plan) - flt(unit.base_price)) < 1,
          {"plan": sum(flt(p.amount) for p in plan), "price": unit.base_price})

    fresh()
    portal = frappe.get_all(
        "Portal User", filters={"parent": CUSTOMER, "parenttype": "Customer"}, pluck="user"
    )
    check("portal login provisioned for the customer", bool(portal), portal)
    if portal:
        check("portal user is a website user, not a desk seat",
              frappe.db.get_value("User", portal[0], "user_type") == "Website User",
              frappe.db.get_value("User", portal[0], "user_type"))

    # the API's own read must agree with the database
    status, detail = call("bookings.get_booking", token=manager, name=BOOKING)
    check("API booking detail matches the plan", len((detail or {}).get("payment_plan", [])) == len(plan), detail and len(detail.get("payment_plan", [])))
    check("API reports collections", "collections" in (detail or {}), list(detail or {})[:10])

    # ------------------------------------------------------------- 5. cancel ----
    fresh()
    status, cancelled = call("bookings.cancel_booking", token=manager, post=True, name=BOOKING, reason="deep verify")
    check("booking cancelled", (cancelled or {}).get("docstatus") == 2, cancelled)
    fresh()
    check("cancelled status persisted",
          frappe.db.get_value("Property Booking", BOOKING, "booking_status") == "Cancelled",
          frappe.db.get_value("Property Booking", BOOKING, "booking_status"))
    check("unit back on the market",
          frappe.db.get_value("Property Unit", unit.name, "availability_status") == "Available",
          frappe.db.get_value("Property Unit", unit.name, "availability_status"))

    print(f"\nPASS {len(PASS)} / {len(PASS) + len(FAIL)}")
    for f in FAIL:
        print("  FAIL:", f)
    print("artifacts:", {"lead": LEAD, "customer": CUSTOMER, "opportunity": OPP, "booking": BOOKING, "unit": unit.name})

    if FAIL:
        raise Exception(f"{len(FAIL)} data checks failed")
    return {"passed": len(PASS)}
