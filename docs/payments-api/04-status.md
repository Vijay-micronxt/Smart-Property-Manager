# 4. `payments.status`

Is it paid, and what is still due. Call it after any payment, or poll it on a
staff screen after sending a link.

```
GET /api/method/property_core.api.payments.status?target=PP-0464
```

| Param | Required | |
|---|---|---|
| `target` | yes | The same `target` the payment was started with |

Response:

```json
{
  "target": "PP-0464",
  "invoice": "ACC-SINV-2026-00254",
  "description": "Booking Amount on BKG-0112",
  "due": 0.0,
  "paid": true
}
```

| Field | |
|---|---|
| `paid` | `true` once nothing is due |
| `due` | ₹ still due (a part payment leaves the rest here) |

For a booking `target`, this is its next unpaid instalment — after one is paid
it moves on to the next, so check `description` too.
