"""
Customer portal API.

Every endpoint is called as::

    /api/method/property_core.api.portal.<module>.<function>

and answers with the same envelope the auth API uses::

    {"status": "ok", "message": null, "data": {...}}

Authentication is either a token (``Authorization: token <key>:<secret>``, get
one from ``property_core.api.auth.login``) or a normal session cookie. There is
no customer parameter anywhere -- the logged-in user resolves to exactly one
Customer, and every query is scoped to it.

Modules:

    meta         settings()             labels, colours, currency, feature flags
    profile      me(), update_contact()
    dashboard    summary()              one call for a home screen
    properties   my_units(), unit(), projects(), site_map(), available_units()
    bookings     list_bookings(), booking_details(), book_unit()
    billing      charges(), maintenance_charges(), utility_bills(), rent_history(),
                 outstanding_dues(), payments(), invoice(), payment_schedule()
    maintenance  work_history(), schedule(), inspections()
    support      issues(), issue(), raise_issue(), add_comment()
    documents    list_documents()

Payload field lists come from ``fields.py`` -- add a field there (or a
``custom_*`` field on the doctype, which is picked up automatically) rather than
editing queries.

The older ``property_core.property_core.api.customer_portal.*`` endpoints still
work and are unchanged; they are what the bundled ``/customer-portal`` page
calls. New clients should use this package.
"""
