"""Row-level visibility on Lead.

The rule now lives in :mod:`property_core.property_core.crm.scope`, which
applies the same hierarchy to Opportunity, Property Booking and Property
Follow Up as well. This module stays as the old entry point so any site
script or Custom DocPerm still pointing here keeps working.
"""

from property_core.property_core.crm.scope import (  # noqa: F401
    UNRESTRICTED_ROLES,
    get_lead_conditions,
    visible_users,
)


def get_permission_query_conditions(user=None):
    return get_lead_conditions(user)


def _visible_users(user):
    return visible_users(user)
