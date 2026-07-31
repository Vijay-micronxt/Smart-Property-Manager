"""Built-in message bodies.

These are the fallback used when no Property Notification Template is defined
for an event+channel, so the system is useful the moment the app is installed.
Create a template to override any of them -- nothing here needs editing.
"""

DEFAULT_TEMPLATES = {
    ("Sales Invoice", "Email"): {
        "subject": "Invoice {{ doc.name }} from {{ company }}",
        "message": """<p>Dear {{ recipient_name }},</p>
<p>Please find attached invoice <b>{{ doc.name }}</b> dated {{ frappe.utils.formatdate(doc.posting_date) }}.</p>
<ul>
  <li>Amount: <b>{{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</b></li>
  <li>Due date: {{ frappe.utils.formatdate(doc.due_date) }}</li>
  {% if property_unit %}<li>Unit: {{ property_unit }}</li>{% endif %}
</ul>
<p>Regards,<br>{{ company }}</p>""",
    },
    ("Sales Invoice", "WhatsApp"): {
        "message": """Dear {{ recipient_name }},

Invoice {{ doc.name }} for {{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }} is ready.
Due date: {{ frappe.utils.formatdate(doc.due_date) }}
{% if property_unit %}Unit: {{ property_unit }}
{% endif %}
Thank you,
{{ company }}""",
    },
    ("Payment Reminder", "Email"): {
        "subject": "{% if days_overdue > 0 %}Overdue: {% endif %}Payment for invoice {{ doc.name }}",
        "message": """<p>Dear {{ recipient_name }},</p>
{% if days_overdue > 0 %}
<p>Our records show invoice <b>{{ doc.name }}</b> is <b>{{ days_overdue }} day(s) overdue</b>.</p>
{% else %}
<p>This is a reminder that invoice <b>{{ doc.name }}</b> is due on {{ frappe.utils.formatdate(due_date) }}.</p>
{% endif %}
<ul>
  <li>Invoice total: {{ frappe.utils.fmt_money(doc.grand_total, currency=doc.currency) }}</li>
  <li>Outstanding: <b>{{ frappe.utils.fmt_money(outstanding, currency=doc.currency) }}</b></li>
  {% if property_unit %}<li>Unit: {{ property_unit }}</li>{% endif %}
</ul>
<p>Please ignore this message if payment has already been made.</p>
<p>Regards,<br>{{ company }}</p>""",
    },
    ("Payment Reminder", "WhatsApp"): {
        "message": """Dear {{ recipient_name }},
{% if days_overdue > 0 %}
Invoice {{ doc.name }} is {{ days_overdue }} day(s) overdue.
{% else %}
Reminder: invoice {{ doc.name }} is due on {{ frappe.utils.formatdate(due_date) }}.
{% endif %}
Outstanding: {{ frappe.utils.fmt_money(outstanding, currency=doc.currency) }}
{% if property_unit %}Unit: {{ property_unit }}
{% endif %}
Please ignore if already paid.

{{ company }}""",
    },
    ("Payment Receipt", "Email"): {
        "subject": "Payment received - receipt {{ doc.name }}",
        "message": """<p>Dear {{ recipient_name }},</p>
<p>We have received your payment of
<b>{{ frappe.utils.fmt_money(doc.paid_amount, currency=doc.paid_from_account_currency) }}</b>
on {{ frappe.utils.formatdate(doc.posting_date) }}. Thank you.</p>
{% if allocated_invoices %}
<p>Applied to:</p>
<ul>
{% for row in allocated_invoices %}
  <li>{{ row.invoice }} &mdash; {{ frappe.utils.fmt_money(row.allocated_amount, currency=doc.paid_from_account_currency) }}
      {% if row.outstanding > 0 %}(balance {{ frappe.utils.fmt_money(row.outstanding, currency=doc.paid_from_account_currency) }}){% else %}(fully paid){% endif %}
  </li>
{% endfor %}
</ul>
{% endif %}
<p>Regards,<br>{{ company }}</p>""",
    },
    ("Payment Receipt", "WhatsApp"): {
        "message": """Dear {{ recipient_name }},

Payment of {{ frappe.utils.fmt_money(doc.paid_amount, currency=doc.paid_from_account_currency) }} received on {{ frappe.utils.formatdate(doc.posting_date) }}.
Receipt: {{ doc.name }}
{% if allocated_invoices %}Applied to: {% for row in allocated_invoices %}{{ row.invoice }}{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
Thank you,
{{ company }}""",
    },
    ("Lead Follow Up", "Email"): {
        "subject": "{% if days_overdue > 0 %}Overdue follow-up{% else %}Follow-up due{% endif %}: {{ doc.lead_name or doc.name }}",
        "message": """<p>Hi {{ recipient_name }},</p>
{% if days_overdue > 0 %}
<p>Follow-up for <b>{{ doc.lead_name or doc.name }}</b> was due on
{{ frappe.utils.formatdate(follow_up_date) }} &mdash; {{ days_overdue }} day(s) ago.</p>
{% else %}
<p>Follow-up for <b>{{ doc.lead_name or doc.name }}</b> is scheduled for
{{ frappe.utils.formatdate(follow_up_date) }}.</p>
{% endif %}
<ul>
  <li>Status: {{ doc.status }}</li>
  {% if doc.mobile_no or doc.phone %}<li>Phone: {{ doc.mobile_no or doc.phone }}</li>{% endif %}
  {% if doc.email_id %}<li>Email: {{ doc.email_id }}</li>{% endif %}
  {% if doc.source %}<li>Source: {{ doc.source }}</li>{% endif %}
</ul>
<p><a href="{{ lead_link }}">Open the lead</a></p>""",
    },
    ("Lead Follow Up", "WhatsApp"): {
        "message": """Hi {{ recipient_name }},
{% if days_overdue > 0 %}
Follow-up OVERDUE by {{ days_overdue }} day(s): {{ doc.lead_name or doc.name }}
{% else %}
Follow-up due {{ frappe.utils.formatdate(follow_up_date) }}: {{ doc.lead_name or doc.name }}
{% endif %}
Status: {{ doc.status }}
{% if doc.mobile_no or doc.phone %}Phone: {{ doc.mobile_no or doc.phone }}
{% endif %}
{{ lead_link }}""",
    },
}


def get_default(event, channel):
    return DEFAULT_TEMPLATES.get((event, channel))
