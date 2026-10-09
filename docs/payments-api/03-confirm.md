# 3. `payments.confirm`

**Checkout popup only.** Not used for links.

Hand the popup's `handler` response back unchanged. The server verifies the
signature with Razorpay and records the payment.

```
POST /api/method/property_core.api.payments.confirm
```

| Param | Required | |
|---|---|---|
| `gateway` | yes | `gateway` from the `start` response |
| `payload` | yes | The popup's response object, untouched |

```json
{
  "gateway": "Razorpay",
  "payload": {
    "razorpay_payment_id": "pay_TlnwQ0N9VR8jVF",
    "razorpay_order_id": "order_TloMzp086bvs4V",
    "razorpay_signature": "88b201ea…"
  }
}
```

Response:

```json
{
  "paid": true,
  "reconciled": true,
  "payment_entry": "ACC-PAY-2026-00030",
  "sales_invoice": "ACC-SINV-2026-00283",
  "gateway_reference": "pay_TlnwQ0N9VR8jVF"
}
```

| Field | |
|---|---|
| `paid` | `true` = money received. `false` = not confirmed, show an error |
| `payment_entry` | Receipt number to show the customer |

If the customer closes the page before `confirm` runs, the Razorpay webhook
records the payment anyway — one receipt, never two. Call
[`status`](04-status.md) to refresh the screen.
