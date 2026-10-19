# Collect a payment by mSwipe link on WhatsApp

This document is for whoever builds the frontend: the CRM app (staff) and the
customer portal. It is complete on its own. Every endpoint, payload and
response below was run against a test site.

The site picks the gateway, not the frontend. On JD it is mSwipe, which offers
**links only**: there is no in-page popup.

---

## 1. The flow

```
 Staff / customer                Frontend                      Backend (property_core)              mSwipe
 ────────────────                ────────                      ───────────────────────              ──────
 1. "Collect payment"  ───────►  GET  payments.options  ─────►  gateway, what is due, mobile
                                 (dialog: amount + mobile,
                                  both editable)
 2. "Create link"      ───────►  POST payments.start    ─────►  checks amount ≤ due  ─────────────►  creates link
                                 ◄── link.url, link.id,         saves an attempt (status
                                     expires_at, share_text     initiated); older unpaid links
                                                                on this invoice → superseded
 3. Frontend sends share_text on WhatsApp (your WhatsApp API, or wa.me) to the mobile
 4. Customer opens the link on their phone and pays on mSwipe's page
 5. Backend records the payment, by whichever comes first:
      a. the customer's browser returns → payments.link_return → asks mSwipe → Payment Entry
         → 302 to your return_url?payment=success|pending|failed&...
      b. your screen polls GET payments.status?target&link_id → backend asks mSwipe → Payment Entry
      c. a job every 5 minutes asks mSwipe about all open links → Payment Entry
 6. GET payments.status shows paid / part paid; the invoice page reloads
```

Paths 5a, 5b and 5c share one settle step, and that step is keyed on the link.
**One payment is never recorded twice**, whichever of them runs and however
often. The backend records a payment only after mSwipe confirms it. It never
trusts the browser.

The customer pays on their own phone and usually never comes back to your
page. That is why **step 5b (polling `status`) is the main path for the
frontend**. Your screen only learns about the payment by calling `status`.

---

## 2. Basics

- Base: `https://<site>/api/method/property_core.api.payments.<fn>`
- Auth: the logged-in user's token: `Authorization: token <api_key>:<api_secret>`.
  - Staff can act on any booking or invoice they can read.
  - A portal customer can act only on their own.
- Every response is wrapped like this. Read `message.data`:

```json
{ "message": { "status": "ok", "message": null, "data": { ... } } }
```

- On an error, the HTTP status is 4xx/5xx and the body has `exc_type`.
  `_server_messages` holds the text to show the user.
- `target` is what is being paid: a Sales Invoice (`ACC-SINV-…`), a Payment Plan
  instalment (`PP-…`) or a Booking (`BKG-…`). A booking means its next unpaid
  instalment.

---

## 3. `GET payments.options`

Call it when the Collect payment dialog opens.

```
GET /api/method/property_core.api.payments.options?target=ACC-SINV-2026-00076
```

```json
{
  "online": true,
  "gateway": { "name": "mSwipe", "modes": ["link"], "needs_phone": true },
  "gateways": [ { "name": "mSwipe", "modes": ["link"], "needs_phone": true } ],
  "instructions": null,
  "due": {
    "target": "ACC-SINV-2026-00076",
    "invoice": "ACC-SINV-2026-00076",
    "description": "ACC-SINV-2026-00076",
    "amount": 2000.0,
    "has_phone": true,
    "phone": "9000000001"
  }
}
```

| Field | Use |
|---|---|
| `online` | `false`: no gateway is set up. Show `instructions`, not a pay button |
| `gateway.modes` | `["link"]` for mSwipe. Do not show a "pay here now" option |
| `gateway.needs_phone` | `true` for mSwipe: `start` must get a mobile number |
| `due.amount` | Prefill the amount field. It is also the maximum |
| `due.phone` | Prefill the mobile field. **Always show it and let the user edit it**: the link is tied to that number. May be `null` |
| `due.description` | e.g. "On Agreement on BKG-0005". Show it in the dialog |

`gateways` is the old list. Ignore it.

---

## 4. `POST payments.start`

Call it when the user taps Create link (or Regenerate link).

```
POST /api/method/property_core.api.payments.start
Content-Type: application/json
```

```json
{
  "target": "ACC-SINV-2026-00076",
  "amount": 500,
  "phone": "98765 43210",
  "return_url": "https://app.example.com/office/billing/invoices/ACC-SINV-2026-00076"
}
```

| Param | Required | |
|---|---|---|
| `target` | yes | |
| `amount` | no | ₹. Defaults to the full amount due. A part payment is fine. More than is due is refused |
| `phone` | **yes for mSwipe** when `has_phone` is false. Otherwise send what is in the mobile field | 10 digits. `+91` and spaces are fine |
| `return_url` | no | Where the customer's browser lands after paying. Its host must be listed under **Allowed Return Hosts** in Property Core Settings |
| `mode` | no | Leave it out. mSwipe always answers with `link` |
| `gateway` | no | Ignored. The site decides |

Response:

```json
{
  "gateway": "mSwipe",
  "mode": "link",
  "amount": 500.0,
  "invoice": "ACC-SINV-2026-00076",
  "link": {
    "url": "https://dcuat.mswipetech.co.in/...TransID=TDB651D7D5CA9",
    "id": "TDB651D7D5CA9",
    "expires_at": "2026-10-20 13:22:30.992849"
  },
  "share_text": "Dear Anita Verma, please pay ₹ 500.00 for ACC-SINV-2026-00076: https://..."
}
```

| Field | Use |
|---|---|
| `link.url` | The payment page. Send it to the customer |
| `link.id` | **Keep it.** Pass it to `status` as `link_id` |
| `link.expires_at` | Site time (IST). Show "valid till …". After it, `status` reports `expired` |
| `share_text` | A ready-made WhatsApp/SMS message that already includes the link |

Each call makes a **new** link and a new attempt record. The older **unpaid**
links on the same invoice become `superseded`, so the customer should use
only the newest one. If an old link is paid anyway, the money is still
recorded. Anything the invoice cannot take stays on the customer as an
advance, and the backend sets it against their next due invoice.

### Sending on WhatsApp

- **Your WhatsApp API:** send `share_text` (or your own template with `link.url`) to the phone.
- **Manual button:** open WhatsApp with everything filled in:

```js
const d = phone.replace(/\D/g, "");
window.open("https://wa.me/" + (d.length === 10 ? "91" + d : d) + "?text=" + encodeURIComponent(data.share_text));
```

- **SMS button:** `location.href = "sms:" + phone + "?body=" + encodeURIComponent(data.share_text)`
- **Copy button:** copy `link.url`.

mSwipe does **not** text the customer itself (`IsSendSMS` is off). Sending the
link is entirely the frontend's job.

### Errors

| Text in `_server_messages` | Meaning |
|---|---|
| `mSwipe needs the customer's mobile number` | No `phone` was sent and none is on file |
| `phone must be a 10-digit mobile number` | |
| `₹X is due on …; a payment cannot be more than that` | Amount is above what is due |
| `Nothing is due on …` | |
| `return_url host … is not allowed …` | Add the host under Allowed Return Hosts |
| `Online payment is not set up …` | No gateway is chosen or set up |
| `Mswipe payment initiation failed: …` / `Mswipe auth failed: …` | mSwipe refused. Show the text. Staff can retry |

---

## 5. `GET payments.status`: did they pay, and how much

This is the API for "did the customer pay, and how much". The backend asks
mSwipe about the open links on `target` **before** answering, and records
any that were paid. So call this and nothing else.

```
GET /api/method/property_core.api.payments.status?target=ACC-SINV-2026-00076&link_id=TDB651D7D5CA9
```

| Param | Required | |
|---|---|---|
| `target` | yes | The same `target` that was passed to `start` |
| `link_id` | no | `link.id` from `start`. With it you get that one link under `link`. Without it you get every link on the target, under `attempts` |

Response (two part payments, invoice now fully paid):

```json
{
  "target": "SINV-26-00067",
  "invoice": "SINV-26-00067",
  "description": "SINV-26-00067",
  "invoice_total": 9600.0,
  "due": 0.0,
  "paid_amount": 9600.0,
  "paid": true,
  "invoice_status": "Paid",
  "link": null,
  "attempts": [
    {
      "link_id": "T16D118251C83",
      "reference": "SINV-26-00067-7e1e76",
      "url": null,
      "target": "SINV-26-00067",
      "invoice": "SINV-26-00067",
      "amount": 5600.0,
      "status": "paid",
      "paid_amount": 5600.0,
      "paid_on": "2026-10-19 13:21:37.336339",
      "payment_entry": "ACC-PAY-2026-00017",
      "created_on": "2026-10-19 13:21:05.963442",
      "expires_at": "2026-10-20 13:21:05.972059"
    },
    {
      "link_id": "TE575134177D3",
      "amount": 4000.0,
      "status": "paid",
      "paid_amount": 4000.0,
      "payment_entry": "ACC-PAY-2026-00016",
      "...": "..."
    }
  ]
}
```

Top level: the invoice.

| Field | |
|---|---|
| `invoice_total` | Invoice grand total |
| `paid_amount` | Total received on the invoice so far, from every payment, not only links |
| `due` | Still due |
| `paid` | `true` when nothing is due |
| `invoice_status` | `Unpaid`, `Partly Paid`, `Paid`, `Overdue` … |
| `link` | With `link_id`: that link's attempt (same shape as below). Otherwise `null` |
| `attempts` | The links on this target, newest first (up to 10) |

Per link (`link` / `attempts[]`):

| `status` | Meaning | Show |
|---|---|---|
| `initiated` | Link sent, not paid yet | "Waiting for payment" |
| `pending` | The customer paid, but the bank has not confirmed yet | "Bank is confirming…" (keep polling) |
| `paid` | Recorded: `paid_amount`, `paid_on`, `payment_entry` are set | "Paid ₹X" |
| `expired` | Past `expires_at`, not paid | "Link expired" + **Regenerate link** |
| `superseded` | A newer link was made for this invoice | "Replaced by a newer link" |
| `failed` | Marked failed | "Failed" + Regenerate |

`url` is filled only while the link can still be paid (`initiated` or `pending`).

A payment that mSwipe declines does **not** make the link `failed`. The link
stays `initiated`, because the customer may try again on the same link.

### Polling rule (staff "Waiting for payment" screen)

```js
// after start():
const linkId = data.link.id, startedAt = Date.now();
const timer = setInterval(async () => {
  const r = await get("payments.status", { target, link_id: linkId });
  const s = r.link.status;
  render(r);                               // see the display table above
  if (s === "paid" || s === "expired" || s === "superseded" || Date.now() - startedAt > 10 * 60 * 1000)
    clearInterval(timer);
  if (s === "paid") reloadInvoice();       // r.paid ? "Paid" : `Part paid, ₹${r.due} still due`
}, 5000);
```

- Poll every 5–10 s. The backend asks mSwipe about one link at most once every
  15 s, however often you poll, so polling faster gains nothing.
- After 10 minutes, stop polling and show a "Check again" button that calls
  `status` once. The 5-minute job keeps recording payments without the screen.
- To show what was paid: `paid` ? "Paid" : `Part paid ₹{link.paid_amount}, ₹{due} still due`.

### Errors

| | |
|---|---|
| `Payment link X is not for Y` | The `link_id` belongs to another target |
| `Payment link X not found` | Unknown `link_id` |
| `Not permitted` | A portal customer asked about someone else's invoice |

---

## 6. The return page (`return_url`)

If the customer comes back in the browser after paying, mSwipe sends them to
the backend. The backend records the payment, then redirects to your
`return_url`:

```
https://app.example.com/office/billing/invoices/ACC-SINV-2026-00076
    ?payment=success&target=ACC-SINV-2026-00076&invoice=ACC-SINV-2026-00076
    &payment_entry=ACC-PAY-2026-00018&amount=500.0
```

| `payment` | |
|---|---|
| `success` | Recorded. `payment_entry` and `amount` are set |
| `pending` | The bank is confirming. Call `status` in a few seconds |
| `failed` | Not paid (declined or cancelled). The link still works |

The query string is only a hint. Call `status` once on that page to show the
real state, and remove the query from the address bar
(`history.replaceState`).

Without `return_url`, the customer sees a plain "Payment received /
processing / not completed" page from the backend.

---

## 7. Every situation

| Situation | What happens | Frontend sees |
|---|---|---|
| Customer pays and comes back | Recorded in 5a. Redirect `payment=success` | Return page, then `status` shows `paid` |
| Customer pays and closes the tab (usual on WhatsApp) | Recorded by your `status` poll (5b) or the 5-minute job (5c) | The polling screen flips to `paid` within ~5–15 s |
| Part payment ₹50,000 of ₹2,00,000 | Invoice becomes Partly Paid, ₹1,50,000 due | `paid:false`, `due:150000`. Make a new link for the balance. Each link is its own attempt |
| Payment declined or abandoned | Nothing is recorded. The link stays usable until `expires_at` | `initiated`. Resend it, or Regenerate |
| Bank has not confirmed yet | Attempt is `pending`. Rechecked until it resolves | `pending`. Keep polling |
| Link expired | `expired`. Still watched for a day, in case it is paid late | Regenerate link |
| New link made while an old one is open | The old one becomes `superseded` | Only the newest link is shown as payable |
| Old (superseded or expired) link paid anyway | Still recorded. The surplus goes as an advance | That attempt shows `paid` |
| Same payment reported twice (return + poll + job) | Recorded once | One `payment_entry` |

---

## 8. Screens to build

### CRM: Collect payment dialog

On a Sales Invoice, Booking or Payment Plan row:

- `options` → amount field (prefilled with `due.amount`, editable, max `due.amount`) and
  mobile field (prefilled with `due.phone`, **always editable**).
- **Create link** → `start` → show:
  - the link, with **Send on WhatsApp**, **Copy link** and **SMS** buttons
  - "valid till `expires_at`"
  - a **Waiting for payment** state that polls `status`
  - a **Regenerate link** button (calls `start` again)
- When paid: show "Paid ₹X" or "Part paid, ₹Y still due", and reload the invoice.

### Customer portal

- Same `options` → `start`. Send `return_url` = the portal page.
- Open `link.url` in the same tab (`location = link.url`). There is no need to
  WhatsApp yourself.
- On return, read `?payment=` and call `status`.

### Invoice / booking page (optional)

`status?target=…` without `link_id` lists every link and its state, which
gives you a payment-link history.

---

## 9. Site setup (backend team, once per site)

- **Property Core Settings → Online Payment Gateway** = `mSwipe`
- **Property Core Settings → Allowed Return Hosts** = the frontend's host, one per line (e.g. `app.example.com`)
- **Mswipe Settings:**
  - API Base URL, Customer Code, API User ID, Client ID, API Password (from mSwipe)
  - Mode of Payment = `Mswipe`, which must have a default account
  - System User
  - **Link Valid For (hours)**: default 24
  - **LinkValidity sent to mSwipe**: blank = mSwipe's own default. Fill it only in the format mSwipe's guide gives
- UAT base URL: `https://dcuat.mswipetech.co.in/ipg/api`. Production comes from mSwipe.
