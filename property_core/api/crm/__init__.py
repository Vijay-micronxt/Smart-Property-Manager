"""Staff-facing CRM API — the funnel from enquiry to booking, as JSON.

    /api/method/property_core.api.crm.<module>.<function>

Everything answers the same envelope as the customer portal API:

    {"status": "ok", "message": null, "data": ...}

Modules:
    session       login, whoami, token refresh
    meta          every dropdown the screens need, in one call
    team          the reporting hierarchy this login can see
    dashboard     scoped KPIs for the logged-in user
    leads         Lead — the top of the funnel
    follow_ups    Property Follow Up — the activity trail that survives conversion
    opportunities Opportunity — requirement agreed, property tagged
    customers     Customer — created from a lead, needed before a booking
    inventory     Project / Property / Property Unit — what is available to sell
    bookings      Property Booking — the deal, its payment plan and collections
    projects      the project-centric roll-up JD runs the business on

Visibility is not re-implemented here: every listing runs through Frappe's
permission engine, which is wired to
``property_core.property_core.crm.scope`` (admin → company, sales manager →
their reporting tree, executive → their own).
"""
