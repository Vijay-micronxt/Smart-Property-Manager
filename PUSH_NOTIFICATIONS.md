# Push notifications — frontend guide

For the CRM app (web / Android / iOS). The server decides **who** gets a push
and **when**; the app only has to:

1. get an FCM token from Firebase and send it to the server after login,
2. remove it on logout,
3. show the push and open the right screen when it is tapped,
4. (optional) show a bell screen with the same notifications.

Everything here uses the same base URL, auth header and response envelope as
the rest of the CRM API (see `CRM_APP_GUIDE.md` §1):

```
Base:     https://<site>/api/method/property_core.api.crm.notifications.<function>
Auth:     Authorization: token <api_key>:<api_secret>      (from session.login)
Reads:    GET  with query-string args
Writes:   POST with JSON body  (Content-Type: application/json)
Payload:  response.message.data
```

---

## 1. Firebase setup (app side)

* Use **one Firebase project** for the app. The server holds that same
  project's *service account* (in **FCM Notification Settings** on the site).
  A token from a different Firebase project is rejected by Google, and the
  push silently never arrives.
* Tell the backend team which Firebase project you are using, so the matching
  service account JSON can be saved on the site.

### Web (PWA / browser)

```js
// firebase v10 modular SDK
import { initializeApp } from "firebase/app";
import { getMessaging, getToken, onMessage, deleteToken } from "firebase/messaging";

const app = initializeApp(firebaseConfig);            // from Firebase console → Project settings → Your apps
const messaging = getMessaging(app);

export async function enablePush() {
  if ((await Notification.requestPermission()) !== "granted") return;
  const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
  const token = await getToken(messaging, {
    vapidKey: "<Web Push certificate key pair>",      // Project settings → Cloud Messaging
    serviceWorkerRegistration: registration,
  });
  await api.post("notifications.register_device", {
    device_token: token,
    device_type: "web",
    device_name: navigator.userAgent.includes("Mobile") ? "mobile" : "desktop",
  });
  localStorage.setItem("fcm_token", token);
}

// app open in the foreground: the browser does NOT show the push by itself
onMessage(messaging, ({ notification, data }) => {
  showToast(notification.title, notification.body, () => openRecord(data));
  refreshBellCount();
});
```

`/firebase-messaging-sw.js` (must be served from the site root):

```js
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.2/firebase-messaging-compat.js");
firebase.initializeApp({ /* same firebaseConfig */ });
const messaging = firebase.messaging();
// background pushes are shown by the browser automatically (they carry a
// "notification" block). Handle the tap:
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const d = event.notification.data?.FCM_MSG?.data || {};
  event.waitUntil(clients.openWindow(routeFor(d.doctype, d.docname)));
});
```

### Android / iOS (React Native shown; Flutter `firebase_messaging` is the same flow)

```js
import messaging from "@react-native-firebase/messaging";

await messaging().requestPermission();               // iOS + Android 13+
const token = await messaging().getToken();
await api.post("notifications.register_device", { device_token: token, device_type: Platform.OS }); // "android" | "ios"

messaging().onTokenRefresh((t) =>
  api.post("notifications.register_device", { device_token: t, device_type: Platform.OS }));

messaging().onMessage(async (msg) => showInAppBanner(msg));               // foreground
messaging().onNotificationOpenedApp((msg) => openRecord(msg.data));       // background → tap
messaging().getInitialNotification().then((msg) => msg && openRecord(msg.data)); // killed → tap
```

Android: the server asks for the sound `cash_notification.wav`. Put that file
in `android/app/src/main/res/raw/` to use it; without it Android plays the
default sound. iOS: same file name in the app bundle, plus the Push
Notifications capability and the APNs key uploaded to Firebase.

---

## 2. When to call what

| Moment | Call |
|---|---|
| After every successful login / app start with a saved session | `register_device` |
| Firebase gives a new token (`onTokenRefresh`) | `register_device` again |
| Logout — **before** clearing the api key | `unregister_device(device_token)` |
| "Log out of all devices" | `unregister_device(all_devices=1)` |
| App start, and when a push arrives in foreground | `unread_count` (bell badge) |
| Bell screen opened | `get_notifications` |
| User taps a notification in the bell list | open the record, then `mark_read(name)` |
| "Mark all read" | `mark_read()` |
| Settings → "Send me a test notification" | `send_test` |

`register_device` is safe to call on every launch: the same token is stored
once, and if another user had registered the same token (shared phone), it
moves to the user now logged in.

---

## 3. Endpoints

### `register_device` — POST

```json
{"device_token": "ftByFzkWH-rlis...", "device_type": "android", "device_name": "Pixel 7"}
```

`device_type`: `android` | `ios` | `web` (default `android`). `device_name` is
optional (free text, shown in `my_devices`).

```json
{"message": {"status": "ok", "message": "Device registered", "data": {"name": "DEV-0007"}}}
```

Already registered → same shape, message `"Device already registered"`.

### `unregister_device` — POST

```json
{"device_token": "ftByFzkWH-rlis..."}
```
or `{"all_devices": 1}`.

```json
{"message": {"status": "ok", "message": null, "data": {"removed": 1}}}
```

### `my_devices` — GET

```json
{"data": [{"name": "DEV-0007", "device_type": "android", "device_name": "Pixel 7", "creation": "2026-10-22 15:10:02"}]}
```

### `get_notifications` — GET

Args: `unread_only` (0/1), `page` (from 1), `page_size` (max 100, default 20).

```json
{"data": {
  "rows": [
    {
      "name": "a1b2c3d4e5",
      "subject": "Follow-up at 03:30 PM: Ramesh Kumar",
      "body": "Call with Ramesh Kumar (Lead CRM-LEAD-2026-00012), scheduled 22 Oct, 03:30 PM.",
      "type": "Alert",
      "document_type": "Lead",
      "document_name": "CRM-LEAD-2026-00012",
      "from_user": "Administrator",
      "read": 0,
      "creation": "2026-10-22 15:15:00.123456"
    }
  ],
  "page": 1, "page_size": 20, "total": 37, "has_more": true,
  "unread": 4
}}
```

`subject` and `body` are plain text (HTML already stripped).

### `unread_count` — GET

```json
{"data": {"unread": 4}}
```

### `mark_read` — POST

`{"name": "a1b2c3d4e5"}` marks one; `{}` marks all.

```json
{"data": {"marked": 1}}
```

### `send_test` — POST

No body. Pushes "Test notification" to every device of the logged-in user.
Fails with a clear message if no device is registered yet.

```json
{"message": {"status": "ok", "message": "Test push queued", "data": {"notification": "a1b2c3d4e5", "devices": 2}}}
```

The push is sent by a background worker — it normally arrives within a few
seconds.

---

## 4. What the push looks like

```json
{
  "notification": {"title": "Lead transferred to you: Ramesh Kumar",
                   "body":  "Tushar gave you Lead CRM-LEAD-2026-00012."},
  "data": {"doctype": "Lead", "docname": "CRM-LEAD-2026-00012"}
}
```

**On tap — route by `data.doctype`:**

| `doctype` | Open |
|---|---|
| `Lead` | lead detail `docname` |
| `Opportunity` | opportunity detail |
| `Property Booking` | booking detail |
| `Property Follow Up` with `docname` = `"None"` | today's follow-ups list (morning digest) |
| `Task`, `Issue`, `Property Work Order`, … | that record's screen if the app has one |
| anything else | the bell screen |

`docname` is always a string; `"None"` means "no single record — open the
list".

---

## 5. Which events push (server side, nothing to build)

| When | Who gets it | Title |
|---|---|---|
| A record is assigned (`activity.assign`, `leads.assign_lead`, `tasks.assign_task`, desk "Assign To") | assignee | "Tushar assigned a new task Lead Ramesh Kumar to you" |
| Assignment removed | previous assignee | "Your assignment on Lead Ramesh Kumar has been removed by Tushar" |
| `leads.transfer_ownership` | new owner + previous assignee | the two texts above, body "Lead transferred to you" |
| Lead / Opportunity owner changed any other way (edit, desk) | new owner + old owner | "Lead transferred to you: …" / "Lead moved: …" |
| Follow-up created or reassigned for someone else | follow-up's `assigned_to` | "New follow-up: Call with Ramesh Kumar" |
| 15 min before an open follow-up | follow-up's `assigned_to` | "Follow-up at 03:30 PM: Ramesh Kumar" (or "Follow-up overdue: …" if late) |
| Every day 7 AM | each user with follow-ups due today / overdue | "Today: 5 follow-ups, 2 overdue" |
| Desk mentions, document shares, any ERPNext *Notification* with channel *System Notification* | that user | Frappe's text |

A user never gets a push for something they did themselves.

Admins control this in **Property Notification Settings → App Push
Notifications** (on/off, morning digest on/off, minutes before a follow-up).
A user who turns off notifications in their own Frappe *Notification
Settings* gets no pushes.

---

## 6. Checklist

- [ ] Firebase project chosen; backend told which one (service account goes on the site)
- [ ] Web: `firebase-messaging-sw.js` at site root, VAPID key in `getToken`
- [ ] Android/iOS: `google-services.json` / `GoogleService-Info.plist`, APNs key in Firebase (iOS)
- [ ] `register_device` after login and on token refresh
- [ ] `unregister_device` on logout
- [ ] Foreground push shown in-app (browser / OS do not show it by themselves)
- [ ] Tap opens the record from `data.doctype` / `data.docname`
- [ ] Bell badge from `unread_count`, list from `get_notifications`, `mark_read`
- [ ] Test with `send_test` on a real device
