# 1. `payments.options`

What the Pay screen needs: is online payment on, through which gateway, and what is due on `target`.

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
  "gateway": { "name": "mSwipe", "modes": ["link"], "needs_phone": true },
  "gateways": [{ "name": "mSwipe", "modes": ["link"], "needs_phone": true }],
  "instructions": "HDFC Bank A/c 50200012345678, IFSC HDFC0001234\nUPI: jdfarms@hdfcbank",
  "due": {
    "target": "PP-0502",
    "invoice": "ACC-SINV-2026-00283",
    "description": "Booking Amount on BKG-0124",
    "amount": 50000.0,
    "has_phone": true,
    "phone": "9000000001"
  }
}
```

| Field | |
|---|---|
| `online` | `false` = no gateway enabled: hide Pay online, show `instructions` (bank / UPI details) instead |
| `gateway` | The gateway set in Property Core Settings (`null` when `online` is false). Display only; never send it back |
| `gateway.modes` | `link`, plus `checkout` for Razorpay |
| `gateway.needs_phone` | `true` = it cannot start without the customer's mobile number |
| `due.has_phone` | `false` = no mobile on file: when `needs_phone`, ask for one and send it as `phone` to `start` |
| `due.phone` | The mobile on file (or `null`): prefill an editable mobile field — the link goes to that number |
| `gateways` | The same gateway as a one-item list, for older frontends |
| `due.amount` | ₹ due now. `0` = nothing to pay, hide the button |
| `due.description` | Show it on the button / screen, e.g. "Booking Amount on BKG-0124" |
