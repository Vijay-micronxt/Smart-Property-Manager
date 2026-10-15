# Payments API — for the frontend

Collect an instalment online from the customer app or the CRM. The frontend uses
**four endpoints**. The same calls work whichever gateway the site has enabled
(Razorpay today); none of them is Razorpay-specific.

| # | Endpoint | Method | Use it to |
|---|---|---|---|
| 1 | [`payments.options`](01-options.md) | GET | Show the Pay button: is a gateway on, how much is due |
| 2 | [`payments.start`](02-start.md) | POST | Start the payment: get a payment link, or the checkout popup options |
| 3 | [`payments.confirm`](03-confirm.md) | POST | Checkout popup only: hand back the popup's result |
| 4 | [`payments.status`](04-status.md) | GET | After paying: is it paid, what is still due |

After a **link** payment the customer is sent back to your page — see
[05-return-page.md](05-return-page.md).

## Basics

| | |
|---|---|
| Base URL | `https://<site>/api/method/property_core.api.payments.<endpoint>` |
| Auth | `Authorization: token <api_key>:<api_secret>`, or the session cookie after `property_core.api.auth.login` |
| Body | `application/json` or form fields |
| Success | HTTP 200, `{"message": {"status": "ok", "message": null, "data": {...}}}` — everything below is `message.data` |
| Error | HTTP 4xx, `{"exception": "...", "_server_messages": "[...]"}` — show the text of `_server_messages` |

**Who may pay what:** a customer logged in to the portal, only their own
bookings and invoices; staff, anything they can read in the CRM.

## `target` — what is being paid

Every endpoint takes a `target`:

| `target` | Pays |
|---|---|
| `BKG-0112` (Property Booking) | its next unpaid instalment |
| `PP-0464` (Payment Plan row) | that instalment |
| `ACC-SINV-2026-00254` (Sales Invoice) | that invoice |

## The two ways to pay

**Link** — a hosted Razorpay page. Open it, or send it on WhatsApp/SMS.

```
options  →  start(mode=link, return_url)  →  customer pays on Razorpay
         →  browser comes back to return_url?payment=success…  →  status
```

**Checkout** — Razorpay's popup inside your page. No redirect.

```
options  →  start(mode=checkout)  →  open popup  →  confirm(popup result)  →  status
```

Either way the server records the Payment Entry and marks the instalment paid;
the frontend never creates payments itself.

## One-time setup (backend, not the frontend)

- **Property Core Settings → Allowed Return Hosts:** add the frontend's domain
  (e.g. `app.example.com`), one per line. `start` refuses a `return_url` on any
  other domain.
- Razorpay keys in **Razorpay Settings**; Razorpay webhook with `payment.captured`
  and `payment_link.paid` ticked (records the payment if the customer closes the
  tab before coming back).
