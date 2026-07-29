# Payment Integration Guide

Pay-by-Link for Razorpay, mSwipe, and Paytm — endpoint reference, curl examples, and integration notes.

Replace `https://your-site.example.com` with your ERPNext site URL throughout.

---

## Table of Contents

1. [Prerequisites & Setup](#1-prerequisites--setup)
2. [Razorpay](#2-razorpay)
   - [Create Order](#21-create-order--get-razorpay-key)
   - [Verify Signature (client-side confirm)](#22-verify-signature-client-side-confirm)
   - [Capture Payment (server confirm + PE creation)](#23-capture-payment-server-confirm--pe-creation)
   - [Webhook](#24-webhook)
3. [mSwipe](#3-mswipe)
   - [Initiate Payment](#31-initiate-payment)
   - [Callback](#32-callback)
4. [Paytm](#4-paytm)
   - [Ecommerce Payment Link (from Sales Order)](#41-ecommerce-payment-link-from-sales-order)
   - [WhatsApp Dealer Dues Link (by phone)](#42-whatsapp-dealer-dues-link-by-phone)
   - [Webhook](#43-webhook)
5. [End-to-End Flows](#5-end-to-end-flows)
6. [Error Responses](#6-error-responses)
7. [API Path Quick Reference](#7-api-path-quick-reference)

---

## 1. Prerequisites & Setup

### Install Python dependency

```bash
# On the Frappe bench server
bench pip install pycryptodome
```

> **Why:** Paytm's AES-128 checksum (`generate_paytm_signature`) uses `pycryptodome`. Without it, any Paytm API call will raise an `ImportError`.

### ERPNext configuration

After `bench get-app` + `bench install-app property_core` + `bench migrate`:

**1. Create Mode of Payment records** (Accounting → Mode of Payment):

| Name | Default Account (per company) |
|---|---|
| `Razorpay` | e.g. Razorpay Clearing Account |
| `Mswipe` | e.g. Mswipe Clearing Account |
| `Paytm` | e.g. Paytm Clearing Account |

**2. Fill Settings single docs** (search each in the desk):

| DocType | Required fields |
|---|---|
| Razorpay Settings | `api_key`, `api_secret`, `system_user` |
| Mswipe Settings | `base_url`, `cust_code`, `user_id`, `client_id`, `password` |
| Paytm Settings | `merchant_id`, `merchant_key`, `payment_account` |

`webhook_secret` in Razorpay Settings is optional but strongly recommended.  
Set `staging = 1` in Paytm Settings to point at `securestage.paytmpayments.com` during testing.

---

## 2. Razorpay

### Flow overview

```
Frontend                  Your server / ERPNext            Razorpay
   |                            |                              |
   |── order_payment ──────────>|── POST /orders ─────────────>|
   |<── {order.id, key} ────────|<── {id, amount, ...} ────────|
   |                            |                              |
   |── open Razorpay SDK ──────────────────────────────────────>|
   |<── payment_id, signature ───────────────────────────────── |
   |                            |                              |
   |── capture_payment ────────>|── GET /payments/{id} ────────>|
   |                            |── create SI + PE             |
   |<── {payment_entry, ...} ───|                              |
```

### 2.1 Create Order & get Razorpay key

Supports `Sales Order`, `Sales Invoice`, or `Quotation` as `order_id`.

**Endpoint:** `POST /api/method/property_core.property_core.api.ecommerce.razorpay_integration.order_payment`  
**Auth:** Guest (no session cookie needed)

```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.razorpay_integration.order_payment" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "SAL-ORD-2026-00042",
    "amount": 25000,
    "store_id": "STORE-01",
    "owner_id": "customer@example.com"
  }'
```

**Success response (HTTP 200):**
```json
{
  "message": {
    "status": 200,
    "data": {
      "order": {
        "id": "order_PkQr7LmNxY2abc",
        "amount": 25000.0,
        "currency": "INR",
        "receipt": "SAL-ORD-2026-00042",
        "transactionId": "order_PkQr7LmNxY2abc"
      }
    },
    "key": "rzp_live_xxxxxxxxxxxx"
  }
}
```

> Use `key` + `data.order.id` to initialise the Razorpay JavaScript SDK on the frontend.

**Error response:**
```json
{
  "message": {
    "status": 400,
    "error": "Razorpay API Key and Secret must be configured in Razorpay Settings"
  }
}
```

---

### 2.2 Verify Signature (client-side confirm)

Call this after the Razorpay SDK returns `razorpay_payment_id`, `razorpay_order_id`, and `razorpay_signature` in the frontend callback.

**Endpoint:** `POST /api/method/property_core.property_core.api.ecommerce.razorpay_integration.verify_payment_signature`  
**Auth:** Guest

```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.razorpay_integration.verify_payment_signature" \
  -H "Content-Type: application/json" \
  -d '{
    "razorpay_payment_id": "pay_PkQr9abcXYZ123",
    "razorpay_order_id":   "order_PkQr7LmNxY2abc",
    "razorpay_signature":  "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
  }'
```

**Success response:**
```json
{
  "message": {
    "success": true,
    "message": "Payment verified",
    "payment_status": "CAPTURED",
    "razorpay_payment_id": "pay_PkQr9abcXYZ123",
    "razorpay_order_id": "order_PkQr7LmNxY2abc"
  }
}
```

> This call also auto-creates the ERPNext Payment Entry if status is `CAPTURED` or `AUTHORIZED` and no PE exists yet.

---

### 2.3 Capture Payment (server confirm + PE creation)

Server-to-server alternative to verify_payment_signature — fetches the payment directly from Razorpay, handles SI + PE creation, and is fully idempotent.

**Endpoint:** `POST /api/method/property_core.property_core.api.ecommerce.razorpay_integration.capture_payment`  
**Auth:** Guest

```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.razorpay_integration.capture_payment" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id":       "SAL-ORD-2026-00042",
    "payment_token":  "pay_PkQr9abcXYZ123",
    "store_id":       "STORE-01",
    "owner_id":       "customer@example.com"
  }'
```

**Success response (new payment):**
```json
{
  "message": {
    "status": 200,
    "is_duplicate": false,
    "data": {
      "payment_id": "pay_PkQr9abcXYZ123",
      "order_id":   "order_PkQr7LmNxY2abc",
      "amount":     25000.0,
      "currency":   "INR",
      "status":     "COMPLETED",
      "payment_entry":  "ACC-PAY-2026-00117",
      "sales_invoice":  "ACC-SINV-2026-00089"
    }
  }
}
```

**Success response (duplicate — PE already exists):**
```json
{
  "message": {
    "status": 200,
    "is_duplicate": true,
    "data": {
      "payment_id":    "pay_PkQr9abcXYZ123",
      "order_id":      "order_PkQr7LmNxY2abc",
      "amount":        25000.0,
      "currency":      "INR",
      "status":        "COMPLETED",
      "payment_entry": "ACC-PAY-2026-00117",
      "sales_invoice": "ACC-SINV-2026-00089"
    }
  }
}
```

---

### 2.4 Webhook

Register this URL in your Razorpay Dashboard → Webhooks:  
`https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.razorpay_webhooks.handle_razorpay_webhook`

Active events: `payment.authorized`, `payment.captured`, `payment.failed`, `refund.created`, `refund.processed`

**Test with curl (simulate `payment.captured`):**

```bash
# Generate the HMAC-SHA256 signature first:
BODY='{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_PkQr9abcXYZ123","order_id":"order_PkQr7LmNxY2abc","amount":2500000,"status":"captured"}}}}'
SECRET="your_webhook_secret_here"
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.razorpay_webhooks.handle_razorpay_webhook" \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: $SIG" \
  -d "$BODY"
```

**Response:**
```json
{ "message": { "status": "success" } }
```

> If `webhook_secret` is not set in Razorpay Settings the signature check is skipped with a warning logged — set it in production.

---

## 3. mSwipe

### Flow overview

```
Your server / ERPNext              mSwipe PBL
   |                                  |
   |── order_payment ────────────────>|  (auth token + initiate)
   |<── {payment_url, trans_id} ──────|
   |                                  |
   Customer pays via link             |
   |                                  |
   |<── callback (encIpgId) ──────────|
   |── check_transaction_status ─────>|  (server-to-server confirm)
   |<── {Payment_Status, IPG_ID} ─────|
   |── create SI + PE                 |
```

### 3.1 Initiate Payment

Accepts `Sales Order`, `Sales Invoice`, or `Quotation` as `order_id`.  
`mobile` is mandatory — mSwipe sends the SMS/link to this number.

**Endpoint:** `POST /api/method/property_core.property_core.api.ecommerce.mswipe_integration.order_payment`  
**Auth:** Guest

```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.mswipe_integration.order_payment" \
  -H "Content-Type: application/json" \
  -d '{
    "order_id":  "SAL-ORD-2026-00042",
    "amount":    25000,
    "mobileno":  "9876543210",
    "email":     "customer@example.com",
    "return_url": "https://your-site.example.com/payment-complete"
  }'
```

**Success response:**
```json
{
  "message": {
    "status": 200,
    "data": {
      "order": {
        "order_id":    "SAL-ORD-2026-00042",
        "amount":      25000.0,
        "payment_url": "https://pbl.mswipetech.com/pay?TransID=TXN123456&...",
        "txn_id":      "TXN123456",
        "trans_id":    "TRANS7890"
      }
    }
  }
}
```

Redirect the customer to `payment_url` or send it via WhatsApp/SMS.

**Error — missing mobile:**
```json
{
  "message": {
    "status": 400,
    "error": "Mobile number is required for Mswipe payment"
  }
}
```

---

### 3.2 Callback

mSwipe redirects the customer's browser to this URL after payment. It also acts as the server-side confirmation trigger (calls `check_transaction_status` internally).

**Endpoint:** `GET /api/method/property_core.property_core.api.ecommerce.mswipe_webhooks.handle_mswipe_callback`  
**Auth:** Guest  
**Query param set by mSwipe:** `encIpgId=<trans_id>`

**Simulate a successful callback:**
```bash
curl -s -G \
  "https://your-site.example.com/api/method/property_core.property_core.api.ecommerce.mswipe_webhooks.handle_mswipe_callback" \
  --data-urlencode "encIpgId=TRANS7890"
```

**Outcome when `return_url` was provided:** Customer is redirected to:
```
https://your-site.example.com/payment-complete?status=TXN_SUCCESS&order_id=SAL-ORD-2026-00042&payment_entry=ACC-PAY-2026-00118&sales_invoice=ACC-SINV-2026-00090
```

**Outcome without `return_url` (JSON response):**
```json
{
  "message": {
    "status": 200,
    "data": {
      "order_id":      "SAL-ORD-2026-00042",
      "status":        "TXN_SUCCESS",
      "payment_entry": "ACC-PAY-2026-00118",
      "sales_invoice": "ACC-SINV-2026-00090"
    }
  }
}
```

**Failed payment redirect:**
```
https://your-site.example.com/payment-complete?status=TXN_FAILURE&order_id=SAL-ORD-2026-00042
```

> mSwipe has no webhook signature. The `check_transaction_status()` server-to-server call is the only trust anchor — it is never skipped.

---

## 4. Paytm

### 4.1 Ecommerce Payment Link (from Sales Order)

Generates a Paytm Pay-by-Link for a submitted Sales Order.  
**Requires an authenticated session** (not guest).

**Endpoint:** `POST /api/method/property_core.property_core.api.paytm_payment_link.generate_ecommerce_payment_link`  
**Auth:** ERPNext session cookie or API key+secret

```bash
# With API key authentication
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.paytm_payment_link.generate_ecommerce_payment_link" \
  -H "Content-Type: application/json" \
  -H "Authorization: token api_key:api_secret" \
  -d '{
    "so_name": "SAL-ORD-2026-00042"
  }'
```

**Success response:**
```json
{
  "message": {
    "link":     "https://paytm.me/ABCD1234",
    "amount":   25000.0,
    "order_id": "ECSAL-ORD20260042420260729143022",
    "message":  "💳 *Payment Link*\nOrder: SAL-ORD-2026-00042\nAmount: ₹25,000.00\n\nPay securely here:\nhttps://paytm.me/ABCD1234\n\nThis link is valid for a limited time."
  }
}
```

The `message` field is ready to paste into WhatsApp.

**Error — order not submitted:**
```json
{
  "exc_type": "ValidationError",
  "exception": "Sales Order must be submitted before generating a payment link"
}
```

---

### 4.2 WhatsApp Dealer Dues Link (by phone)

Looks up the customer by phone number, sums all outstanding Sales Invoices, and generates a single Paytm link for the total. Designed to be called from a WhatsApp bot or chatbot flow.

**Endpoint:** `POST /api/method/property_core.property_core.api.paytm_payment_link.generate_payment_link`  
**Auth:** Guest

```bash
# Phone passed in body
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.paytm_payment_link.generate_payment_link" \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+91 98765 43210"
  }'
```

**Also accepted — nested under `lead`:**
```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.paytm_payment_link.generate_payment_link" \
  -H "Content-Type: application/json" \
  -d '{
    "lead": { "phone": "9876543210" }
  }'
```

**Success — outstanding dues:**
```json
{
  "message": {
    "status": "ok",
    "amount": 62500.0,
    "link":   "https://paytm.me/XYZ9876",
    "order_id": "WAKamalJain20260729143155",
    "message": "💳 *Payment Link*\nCustomer: Kamal Jain\nTotal Outstanding: ₹62,500.00\n\nPay securely here:\nhttps://paytm.me/XYZ9876\n\nThis link is valid for a limited time."
  }
}
```

**Success — nothing owed:**
```json
{
  "message": {
    "status": "ok",
    "amount": 0,
    "message": "No outstanding dues for customer Kamal Jain"
  }
}
```

**Error — customer not found:**
```json
{
  "message": {
    "status": "error",
    "message": "No customer found for phone ending in 9876543210"
  }
}
```

---

### 4.3 Webhook

Register in your Paytm Dashboard as the `callbackUrl`. Paytm retries on non-200, so this endpoint **always returns HTTP 200** — success/failure is reported in the JSON body.

**Endpoint:** `POST /api/method/property_core.property_core.api.paytm_payment_webhook.handle_link_payment`  
**Auth:** Guest

**Simulate a successful callback (Paytm format):**
```bash
curl -s -X POST \
  "https://your-site.example.com/api/method/property_core.property_core.api.paytm_payment_webhook.handle_link_payment" \
  -H "Content-Type: application/json" \
  -d '{
    "body": {
      "orderId":   "ECSAL-ORD20260042420260729143022",
      "txnId":     "PAYTM_TXN_20260729_001",
      "txnAmount": "25000.00",
      "resultInfo": {
        "resultStatus": "TXN_SUCCESS",
        "resultCode":   "01",
        "resultMsg":    "Txn Success"
      }
    },
    "head": {
      "tokenType": "AES",
      "signature": "..."
    }
  }'
```

**Response — new payment credited:**
```json
{
  "message": {
    "status":        "ok",
    "payment_entry": "ACC-PAY-2026-00119",
    "sales_invoice": "ACC-SINV-2026-00091"
  }
}
```

**Response — already processed (idempotent):**
```json
{
  "message": {
    "status": "ok",
    "reason": "already_processed"
  }
}
```

**Response — payment pending / not yet successful:**
```json
{
  "message": {
    "status":     "pending",
    "txn_status": "PENDING",
    "message":    "Transaction is pending"
  }
}
```

> The webhook always calls `_confirm_order_status()` server-to-server before creating any records — the `body` from Paytm's POST is never trusted alone.

---

## 5. End-to-End Flows

### Razorpay (web checkout)

```
1. POST order_payment          → get Razorpay order ID + key
2. Open Razorpay JS SDK        → customer pays
3. SDK callback: payment_id, order_id, signature
4. POST capture_payment        → SI + Payment Entry created
5. Redirect customer to success page
```

### mSwipe (SMS/WhatsApp link)

```
1. POST order_payment          → get payment_url + trans_id
2. Send payment_url to customer via SMS/WhatsApp
3. Customer pays via link
4. mSwipe redirects browser to callback URL (encIpgId=trans_id)
5. handle_mswipe_callback:
     - check_transaction_status()   ← server-to-server confirm
     - create SI + PE
     - redirect customer to return_url?status=TXN_SUCCESS&...
```

### Paytm ecommerce (SO-based)

```
1. POST generate_ecommerce_payment_link  → get link + order_id cached
2. Share link with customer
3. Customer pays
4. Paytm POSTs to handle_link_payment:
     - _confirm_order_status()            ← server-to-server confirm
     - create SI (from SO) + PE
     - return {status:"ok", ...}
```

### Paytm dealer dues (WhatsApp bot)

```
1. WhatsApp message arrives with phone number
2. POST generate_payment_link (phone)
     → looks up Customer → sums outstanding SIs → creates link
3. Bot sends message.message to customer
4. Paytm webhook → _handle_dealer_dues → PE allocated across SIs oldest-first
```

---

## 6. Error Responses

### Razorpay / mSwipe (return dict pattern)
Both gateways use `{"status": 400, "error": "..."}` — they never throw HTTP 4xx so the client can read the error message.

### Paytm (frappe.response["message"] pattern)
Paytm functions set `frappe.response["message"]` directly. Check the `status` key:

| `status` | Meaning |
|---|---|
| `"ok"` | Payment confirmed and recorded |
| `"pending"` | Paytm returned non-TXN_SUCCESS; no PE created |
| `"error"` | Exception — check ERPNext Error Log for traceback |

### HTTP vs application errors
All endpoints return HTTP 200. Check the response body `status` / `success` key:

```bash
# Example: check if the call succeeded
curl -s ... | python3 -c "
import json,sys
r = json.load(sys.stdin)['message']
if r.get('status') not in (200, 'ok', True):
    print('FAILED:', r)
    sys.exit(1)
print('OK:', r)
"
```

---

## 7. API Path Quick Reference

| Gateway | Action | Method | Path |
|---|---|---|---|
| Razorpay | Create order | POST | `/api/method/property_core.property_core.api.ecommerce.razorpay_integration.order_payment` |
| Razorpay | Verify signature | POST | `/api/method/property_core.property_core.api.ecommerce.razorpay_integration.verify_payment_signature` |
| Razorpay | Capture + create PE | POST | `/api/method/property_core.property_core.api.ecommerce.razorpay_integration.capture_payment` |
| Razorpay | Webhook | POST | `/api/method/property_core.property_core.api.ecommerce.razorpay_webhooks.handle_razorpay_webhook` |
| mSwipe | Initiate link | POST | `/api/method/property_core.property_core.api.ecommerce.mswipe_integration.order_payment` |
| mSwipe | Payment callback | GET | `/api/method/property_core.property_core.api.ecommerce.mswipe_webhooks.handle_mswipe_callback` |
| Paytm | SO payment link | POST | `/api/method/property_core.property_core.api.paytm_payment_link.generate_ecommerce_payment_link` |
| Paytm | Dues link (phone) | POST | `/api/method/property_core.property_core.api.paytm_payment_link.generate_payment_link` |
| Paytm | Webhook | POST | `/api/method/property_core.property_core.api.paytm_payment_webhook.handle_link_payment` |

---

## See also

- [README.md](README.md) — installation and module overview
- [FEATURES.md](FEATURES.md) — full DocType field reference
- [HOW_TO_USE.md](HOW_TO_USE.md) — day-to-day workflow
