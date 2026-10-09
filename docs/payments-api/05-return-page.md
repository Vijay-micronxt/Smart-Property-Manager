# 5. The return page (link payments)

You build this page; nothing to call to get here.

1. You pass `return_url` to [`start`](02-start.md), e.g.
   `https://app.example.com/payment-result`.
2. The customer pays on Razorpay's page.
3. Razorpay sends the browser to the site
   (`property_core.api.payments.link_return` — called by Razorpay, not by you).
   The site checks Razorpay's signature, records the Payment Entry and marks
   the instalment paid.
4. The site redirects the browser to your `return_url` with:

```
https://app.example.com/payment-result?payment=success&target=PP-0464&invoice=ACC-SINV-2026-00254&payment_entry=ACC-PAY-2026-00030&amount=100000.0
```

| Query param | |
|---|---|
| `payment` | `success` — paid and recorded<br>`pending` — bank has not confirmed yet; it is recorded automatically once it does<br>`failed` — not paid, or could not be verified |
| `target` | What was paid |
| `invoice` | The instalment's invoice |
| `payment_entry` | Receipt number (on `success`) |
| `amount` | ₹ paid |

On that page:

```js
const q = new URLSearchParams(location.search);
const result = q.get("payment");             // success | pending | failed
if (result) {
  history.replaceState(null, "", location.pathname);   // a refresh should not show it again
  showResult(result, q.get("target"), q.get("payment_entry"), q.get("amount"));
  refresh(q.get("target"));                  // call payments.status — the URL alone proves nothing
}
```

No `return_url` (e.g. a link staff sent on WhatsApp): the customer sees a plain
"Payment received" page on the site instead.

If your `return_url` already has a query string, the parameters are appended
with `&`.
