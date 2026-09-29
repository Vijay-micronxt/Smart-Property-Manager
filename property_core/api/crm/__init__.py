"""Staff-facing CRM API — the funnel from enquiry to booking, as JSON.

    /api/method/property_core.api.crm.<module>.<function>

Everything answers the same envelope as the customer portal API:

    {"status": "ok", "message": null, "data": ...}

Modules:
    session       login, whoami, token refresh
    meta          every dropdown the screens need, in one call
    team          the reporting hierarchy this login can see
    dashboard     scoped KPIs, lead dashboard, whole-flow dashboard, trend
    leads         Lead — the top of the funnel
    follow_ups    Property Follow Up — the activity trail that survives conversion
    opportunities Opportunity — requirement agreed, property tagged
    customers     Customer — created from a lead, needed before a booking
    inventory     Project / Property / Property Unit — what is available to sell
    bookings      Property Booking — the deal, its payment plan and collections
    projects      the project-centric roll-up JD runs the business on; create/update
    tasks         ERPNext Task under a project, assigned through ToDo
    templates     payment plan + maintenance (recurring charge) templates
    allocations   Property Allocation + Property Agreement (after the sale)
    billing       milestone / ad-hoc invoices, payments, booking statement
    files         attachments on records + Frappe Drive folders
    layout        plot layout, site map, map search
    maintenance   maintenance visits per unit: auto-opened tasks, updates, photo proof
    operations    Issue + Work Order
    activity      comments, assignment, timeline on any record

Visibility is not re-implemented here: every listing runs through Frappe's
permission engine, which is wired to
``property_core.property_core.crm.scope`` (admin → company, sales manager →
their reporting tree, executive → their own).
"""
