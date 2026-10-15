# 2. `payments.start`

Start a payment. Returns a payment link, or the options for the checkout popup.

```
POST /api/method/property_core.api.payments.start
```

| Param | Required | |
|---|---|---|
| `target` | yes | Booking / Payment Plan / Sales Invoice |
| `mode` | no | `link` or `checkout` (default `checkout`) |
| `amount` | no | ₹. Default = everything due on the instalment; more than that is refused |
| `gateway` | no | e.g. `Razorpay`. Default = first enabled gateway for that mode |
| `return_url` | no, `link` only | Your page the customer lands on after paying. See [05-return-page.md](05-return-page.md) |

`return_url` must be a path on the site (`/customer-portal`) or a URL whose
domain is in **Allowed Return Hosts**. Otherwise:
`return_url host app.example.com is not allowed. Add it under Allowed Return Hosts in Property Core Settings.`

## `mode=link`

```json
{
  "target": "PP-0464",
  "mode": "link",
  "amount": 100000,
  "return_url": "https://app.example.com/payment-result"
}
```

Response:

```json
{
  "gateway": "Razorpay",
  "mode": "link",
  "amount": 100000.0,
  "invoice": "ACC-SINV-2026-00254",
  "link": { "url": "https://rzp.io/rzp/pKQ8S9wS", "id": "plink_TlntQZkE7I8ljM", "expires_at": 0 },
  "share_text": "Dear Tushar Patel, please pay ₹ 1,00,000.00 for Booking Amount on BKG-0112: https://rzp.io/rzp/pKQ8S9wS"
}
```

Open `link.url` (`window.location = link.url`), or send `share_text`:

```js
window.open("https://wa.me/91" + phone + "?text=" + encodeURIComponent(data.share_text));
```

## `mode=checkout`

```json
{ "target": "PP-0502", "mode": "checkout" }
```

Response:

```json
{
  "gateway": "Razorpay",
  "mode": "checkout",
  "amount": 50000.0,
  "invoice": "ACC-SINV-2026-00283",
  "checkout": {
    "script": "https://checkout.razorpay.com/v1/checkout.js",
    "options": {
      "key": "rzp_test_xxxxxxxx",
      "order_id": "order_TloMzp086bvs4V",
      "amount": 5000000,
      "currency": "INR",
      "name": "TP Private Limited",
      "description": "Booking Amount on BKG-0124",
      "prefill": { "name": "…", "email": "…", "contact": "" },
      "notes": { "target": "PP-0502" }
    },
    "confirm_fields": ["razorpay_payment_id", "razorpay_order_id", "razorpay_signature"]
  }
}
```

Load `checkout.script` once, open the popup with `checkout.options` as-is, and
send its result to [`confirm`](03-confirm.md):

```js
new Razorpay({
  ...data.checkout.options,
  handler: (resp) => confirmPayment(data.gateway, resp),   // see 03-confirm.md
  modal: { ondismiss: () => showToast("Payment cancelled") },
}).open();
```

`options.amount` is in paise — leave it as it is.
