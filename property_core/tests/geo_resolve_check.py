"""What the map search must be able to swallow.

Everything a person actually has to hand when they know where a plot is: a
pasted coordinate pair, a long Google Maps URL, the short maps.app.goo.gl link
from WhatsApp, and a place name. The short link is the one that used to come
back "Nothing found" — it carries no coordinates at all until the redirect is
followed.

    bench --site review.site execute property_core.tests.geo_resolve_check.run

The link and place-name cases need outbound internet; without it they are
reported as skipped rather than failed.
"""

import frappe

from property_core.property_core import geo

OFFLINE_HINT = ("could not be opened", "Could not reach the map search")


def run():
    passed, failed, skipped = [], [], []

    def case(label, query, expect=None, needs_network=False):
        try:
            result = geo.resolve(query)["results"][0]
        except Exception as e:
            message = str(e)
            if needs_network and any(hint in message for hint in OFFLINE_HINT):
                skipped.append(f"{label} (no internet)")
                return
            failed.append(f"{label}: {type(e).__name__} {message[:120]}")
            return

        if expect:
            lat, lng = expect
            close = abs(result["latitude"] - lat) < 0.01 and abs(result["longitude"] - lng) < 0.01
            (passed if close else failed).append(
                label if close else f"{label}: got {result['latitude']}, {result['longitude']}"
            )
        else:
            (passed if result.get("latitude") else failed).append(label)

    case("coordinates pasted plain", "18.643818754140014, 81.26262995758997", (18.6438, 81.2626))
    case("coordinates with a space", "  12.9716 , 77.5946 ", (12.9716, 77.5946))
    case("long Google Maps URL", "https://www.google.com/maps/search/18.642452,+81.260949?entry=tts", (18.6424, 81.2609))
    case("map URL with an @ pin", "https://www.google.com/maps/@12.9716,77.5946,15z", (12.9716, 77.5946))
    case("shortened WhatsApp link", "https://maps.app.goo.gl/b2CTUbAooneHCcWx7", (18.6424, 81.2609), needs_network=True)
    case("place name", "Nandi Hills Karnataka", None, needs_network=True)

    # a link off the allow-list must never be fetched by the server
    try:
        geo.resolve("http://127.0.0.1:8003/api/method/ping")
        failed.append("internal URL was fetched")
    except frappe.ValidationError:
        passed.append("internal URL refused")

    print(f"PASS {len(passed)} / {len(passed) + len(failed)}" + (f"  (skipped {len(skipped)})" if skipped else ""))
    for row in failed:
        print("  FAIL:", row)
    for row in skipped:
        print("  SKIP:", row)

    if failed:
        raise Exception(f"{len(failed)} map checks failed")
    return {"passed": len(passed), "skipped": len(skipped)}
