# 4. `payments.status`

Did the customer pay, how much, and what is still due. Call it after any
payment, and poll it (every 5–10 s) on a staff screen after sending a link.
Before answering, the backend asks the gateway about the open links on
`target` and records any that were paid, so a customer who paid on their
phone and never came back still shows as paid.

```
GET /api/method/property_core.api.payments.status?target=PP-0464&link_id=TDB651D7D5CA9
```

| Param | Required | |
|---|---|---|
| `target` | yes | The same `target` the payment was started with |
| `link_id` | no | `link.id` from `start`: report that link under `link` |

Response:

```json
{
  "target": "PP-0464",
  "invoice": "ACC-SINV-2026-00254",
  "description": "Booking Amount on BKG-0112",
  "invoice_total": 200000.0,
  "due": 150000.0,
  "paid_amount": 50000.0,
  "paid": false,
  "invoice_status": "Partly Paid",
  "link": {
    "link_id": "TDB651D7D5CA9", "url": null, "amount": 50000.0,
    "status": "paid", "paid_amount": 50000.0, "paid_on": "2026-10-19 13:21:37",
    "payment_entry": "ACC-PAY-2026-00018", "created_on": "2026-10-19 13:21:05",
    "expires_at": "2026-10-20 13:21:05", "target": "PP-0464", "invoice": "ACC-SINV-2026-00254"
  },
  "attempts": [ "…every link on the target, newest first, same shape as link…" ]
}
```

| Field | |
|---|---|
| `paid` | `true` once nothing is due |
| `due` | ₹ still due (a part payment leaves the rest here) |
| `paid_amount` | ₹ received on the invoice so far |
| `link.status` | `initiated` · `pending` · `paid` · `failed` · `expired` · `superseded` |

`attempts` is filled for gateways that keep a record per link (mSwipe);
Razorpay returns `[]`.

For a booking `target` without `link_id`, the invoice is its next unpaid
instalment — after one is paid it moves on to the next, so check
`description` too. With `link_id`, the numbers are for the invoice that link
was raised on.
