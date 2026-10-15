# 1. `payments.options`

What the Pay screen needs: which gateways are on, and what is due on `target`.

```
GET /api/method/property_core.api.payments.options?target=PP-0502
```

| Param | Required | |
|---|---|---|
| `target` | no | Booking / Payment Plan / Sales Invoice. Without it, `due` is left out. |

## Response (`message.data`)

```json
{
  "online": true,
  "gateways": [{ "name": "Razorpay", "modes": ["checkout", "link"] }],
  "instructions": "HDFC Bank A/c 50200012345678, IFSC HDFC0001234\nUPI: jdfarms@hdfcbank",
  "due": {
    "target": "PP-0502",
    "invoice": "ACC-SINV-2026-00283",
    "description": "Booking Amount on BKG-0124",
    "amount": 50000.0
  }
}
```

| Field | |
|---|---|
| `online` | `false` = no gateway enabled: hide Pay online, show `instructions` (bank / UPI details) instead |
| `gateways[].modes` | `checkout` and/or `link` — what `start` accepts for that gateway |
| `due.amount` | ₹ due now. `0` = nothing to pay, hide the button |
| `due.description` | Show it on the button / screen, e.g. "Booking Amount on BKG-0124" |
