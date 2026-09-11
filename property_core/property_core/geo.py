"""Finding a place on the map without scrolling to it.

Frappe's Geolocation control is a bare Leaflet canvas: it draws what you put on
it and gives you no way to go anywhere. On a country-sized map that means
dragging from the middle of India to your layout every single time.

So three ways in, all of which end at the same marker:

  * a place name, geocoded through OpenStreetMap's Nominatim
  * coordinates pasted as "12.9716, 77.5946"
  * a Google Maps link, which is what people actually have in WhatsApp

And one way out: latitude, longitude and a Google Maps link kept on the
document, so a list view, a report, the portal and the field agent's phone can
all reach the spot without opening the map at all.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import flt

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GOOGLE_MAPS = "https://www.google.com/maps/search/?api=1&query={lat},{lng}"

# "@12.9716,77.5946", "?query=12.9716,77.5946", "!3d12.9716!4d77.5946", bare
# pairs. The parameter name is left open on purpose -- Google uses query, q,
# ll, daddr and destination depending on which button produced the link, and
# our own map_link uses query.
_COORD_PATTERNS = (
    re.compile(r"[@?&](?:[a-z_]+=)?(-?\d{1,3}\.\d+),\s*(-?\d{1,3}\.\d+)"),
    re.compile(r"!3d(-?\d{1,3}\.\d+)!4d(-?\d{1,3}\.\d+)"),
    re.compile(r"^\s*(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$"),
)

LOCATION_DOCTYPES = ("Property", "Property Unit")


def parse_coordinates(text):
    """(lat, lng) out of pasted coordinates or a Google Maps link, else None."""
    if not text:
        return None

    for pattern in _COORD_PATTERNS:
        match = pattern.search(str(text))
        if match:
            lat, lng = flt(match.group(1)), flt(match.group(2))
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                return lat, lng

    return None


def extract_point(geo_location):
    """The marker on a Frappe Geolocation value, as (lat, lng).

    Frappe stores GeoJSON with coordinates in [lng, lat] order. A shape rather
    than a point gives back its first vertex, which is close enough to put a
    pin on.
    """
    if not geo_location:
        return None

    try:
        data = json.loads(geo_location) if isinstance(geo_location, str) else geo_location
    except (ValueError, TypeError):
        return None

    for feature in (data or {}).get("features") or []:
        coords = ((feature or {}).get("geometry") or {}).get("coordinates")
        while isinstance(coords, list) and coords and isinstance(coords[0], list):
            coords = coords[0]
        if isinstance(coords, list) and len(coords) >= 2:
            return flt(coords[1]), flt(coords[0])

    return None


def point_geojson(lat, lng):
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"point_type": "marker"},
                    "geometry": {"type": "Point", "coordinates": [flt(lng), flt(lat)]},
                }
            ],
        }
    )


def sync_location_fields(doc, method=None):
    """Keep latitude / longitude / map link in step with the map."""
    if not doc.meta.has_field("latitude"):
        return

    point = extract_point(doc.get("geo_location"))

    if not point:
        doc.latitude = None
        doc.longitude = None
        doc.map_link = None
        return

    lat, lng = point
    doc.latitude = lat
    doc.longitude = lng
    doc.map_link = GOOGLE_MAPS.format(lat=lat, lng=lng)


@frappe.whitelist()
def resolve(query):
    """Turn whatever the user pasted or typed into a marker.

    Coordinates and links are handled here without troubling anyone's server;
    only a place name goes out to Nominatim.
    """
    query = (query or "").strip()
    if not query:
        frappe.throw(_("Type a place, coordinates, or paste a Google Maps link."))

    point = parse_coordinates(query)
    if point:
        lat, lng = point
        return {
            "results": [
                {
                    "label": f"{lat}, {lng}",
                    "latitude": lat,
                    "longitude": lng,
                    "geo_location": point_geojson(lat, lng),
                    "source": "coordinates",
                }
            ]
        }

    return {"results": geocode(query)}


def geocode(query, limit=5):
    """Place name -> candidates, via OpenStreetMap's Nominatim.

    Cached for a day: the same layout gets searched repeatedly, and Nominatim
    asks callers not to hammer it.
    """
    cache_key = f"property_core:geocode:{query.lower()}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached

    try:
        import requests

        response = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": limit, "addressdetails": 0},
            headers={"User-Agent": f"property_core/{frappe.local.site}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Geocode lookup failed")
        frappe.throw(
            _("Could not reach the map search just now. Paste coordinates or a Google Maps link instead.")
        )

    results = []
    for row in payload or []:
        lat, lng = flt(row.get("lat")), flt(row.get("lon"))
        results.append(
            {
                "label": row.get("display_name"),
                "latitude": lat,
                "longitude": lng,
                "geo_location": point_geojson(lat, lng),
                "source": "nominatim",
            }
        )

    if not results:
        frappe.throw(_("Nothing found for '{0}'. Try a landmark, or paste coordinates.").format(query))

    frappe.cache().set_value(cache_key, results, expires_in_sec=86400)
    return results


LOCATION_FIELDS = [
    {
        "fieldname": "latitude",
        "fieldtype": "Float",
        "label": "Latitude",
        "precision": "6",
        "read_only": 1,
        "description": "Taken from the map. Use Set Location to change it.",
    },
    {
        "fieldname": "longitude",
        "fieldtype": "Float",
        "label": "Longitude",
        "precision": "6",
        "read_only": 1,
    },
    {
        "fieldname": "map_link",
        "fieldtype": "Data",
        "label": "Google Maps",
        "read_only": 1,
        "options": "URL",
    },
]
