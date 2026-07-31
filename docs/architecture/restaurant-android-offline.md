# Restaurant POS Android POS — Offline-first Architecture

## Objective

Create an installable Android cashier app for Restaurant POS that keeps selling when connectivity drops and synchronizes every accepted payment exactly once when the API becomes reachable again.

The first pilot targets one Android cashier device per branch. A cashier must complete an online login and open a shift before offline selling is enabled. Cash and cashier-confirmed PromptPay are supported while offline; void, refund, loyalty redemption, and credit operations remain online-only in the pilot.

## Current baseline

The existing repository already provides:

- React/Vite cashier interfaces and PWA assets.
- IndexedDB persistence through Dexie.
- Product, category, unit, stock snapshot, held bill, pending sale, and completed order stores for the generic POS.
- An online/offline indicator and a foreground sync trigger.
- Idempotent generic POS sales through `client_order_id`.
- Restaurant POS-specific menu, queue, recipe stock posting, branch stock isolation, and cashier attribution.

Before this work, the Restaurant POS store order workflow was online-only: its request contract did not carry an idempotency key, and its dining session, queue, sale, payment, and recipe stock operations could not be replayed safely after a connection failure.

## Implementation status — 22 July 2026

Implemented in the current development branch:

- Per-cashier, per-branch restaurant menu/shift/location snapshots in IndexedDB.
- Durable Restaurant POS paid-order outbox with `pending`, `syncing`, `needs_review`, and `synced` states.
- Queue-first checkout, short network timeout, reconnect/resume sync, and manual retry.
- Batch API (maximum 50), `client_order_id` idempotency, canonical acknowledgements, and local print-state replay.
- Logout and shift-close guards while any local sale is unacknowledged.
- Capacitor 7 Android shell (`com.chaiyanutaiagent.restaurant`), Network/App lifecycle plugins, HTTPS-only traffic, and disabled Android backup.
- A compiled debug APK for native build verification.

Still required before a production pilot:

- Production domain, trusted TLS, final API URL, and production CORS update.
- Physical Android device offline UAT, final app icon, printer integration, and release signing.
- Secure native credential storage and an explicit offline-authorization expiry policy.
- A native persistent worker if synchronization must occur while the app is fully terminated. The current pilot synchronizes while open, on reconnection, and on resume; queued rows survive termination and synchronize on the next launch.

## Pilot guarantees

1. The last successfully downloaded branch menu remains usable without the API.
2. A paid order is committed to local durable storage before the UI clears the cart or prints a receipt.
3. Every local order has a globally unique `client_order_id` generated from the installation ID and a UUID.
4. Replaying the same order returns the previously created server order and never posts stock twice.
5. The app displays pending and failed sync counts; failures are never silently discarded.
6. App reloads and Android process restarts do not remove pending orders.
7. A shift cannot be closed on the server until all local paid orders for that shift are acknowledged.
8. The server remains authoritative for canonical order numbers, stock, reports, and conflict resolution.

## Architecture

```text
Restaurant POS cashier UI
        |
        | read/write first
        v
Local data layer
  - menu snapshot
  - branch/shift snapshot
  - paid order outbox
  - sync attempts and acknowledgements
        |
        | API health confirmed
        v
Foreground/resume sync engine
  - persistent native worker is a later hardening step
        |
        v
HTTPS API
  - validate device/user/branch
  - idempotent order creation
  - dining session + queue
  - sale + payment
  - recipe/store stock posting
  - per-order acknowledgement
```

The web pilot uses Dexie as the local data adapter. The Android shell uses the same durable outbox. A later native worker can move the queue to Room/SQLite behind the same repository boundary when background synchronization after process termination becomes a rollout requirement.

## Local records

### Installation profile

- `installation_id`: UUID generated once per app installation.
- `device_code`: human-readable code assigned by an administrator later.
- `app_version`: build version reported during synchronization.
- `last_bootstrap_at`: last successful branch data bootstrap.

### Cached restaurant menu

- Brand, branch, store location, and cashier context.
- Product ID, SKU, name, selling price, menu order, and active status.
- Snapshot version and download timestamp.

### Offline order outbox

- `client_order_id`
- installation, company, brand, branch, location, shift, and cashier IDs
- local receipt and queue labels
- captured menu items and prices
- payment records
- local creation time
- sync state: `pending`, `syncing`, `synced`, or `needs_review`
- retry count, next retry time, last HTTP status, and last error
- canonical server session, sale order, order number, and queue after acknowledgement

The outbox retains acknowledged rows for local history. Cleanup is a separate retention task and must never delete `pending`, `sending`, or `needs_review` records.

## Synchronization contract

### Bootstrap

The online bootstrap returns all branch-scoped data needed to sell:

- brand and branch identity
- store stock location
- open cashier shift
- active restaurant menu snapshot
- payment configuration
- offline policy and expiry
- server time and snapshot version

### Push

`POST /api/v1/restaurant/store/{brand_slug}/orders/sync` accepts a bounded batch. Each order includes `client_order_id`, `local_created_at`, an optional local receipt label, items, and payments.

The API returns one acknowledgement per submitted order:

- `client_order_id`
- `status`: `synced` or `needs_review`
- canonical Restaurant POS order when synchronized
- a safe operator-facing error when review is required

An order is committed independently so one rejected order does not discard acknowledgements for the rest of the batch.

### Idempotency

`sale_orders(company_id, client_order_id)` is already unique. Restaurant POS synchronization must check this key before creating a dining session. When a sale already exists, the linked dining session is loaded and returned. Recipe stock posting must also remain idempotent.

Concurrent requests with the same key may race. The database unique constraint is the final guard; the losing request reloads and returns the committed order.

## Connectivity rules

`navigator.onLine` or a native network callback is only a hint. The app considers the API available only after a short health probe succeeds. A foreground sync runs on:

- app start/resume
- successful login/bootstrap
- native network reconnection
- manual retry
- completion of a paid order while online

The current pilot uses an eight-second sync request timeout and retains failed rows for reconnect/resume/manual retry. Exponential backoff with jitter belongs with the future persistent worker. Authorization failures retain the queue; validation, stale shift, price, or stock conflicts move only the affected order to `needs_review`.

## Stock conflict policy

A cashier may have accepted real payment while offline. Synchronization must not silently lose that sale. The pilot records the order and surfaces any stock posting conflict for manager review. Cached stock is advisory and updated immediately on the device, but multiple offline devices cannot guarantee a shared real-time balance.

The one-device-per-branch pilot reduces this conflict. Multi-device rollout requires device-prefixed local queues and an approved negative-stock/reconciliation policy.

## Authentication and shifts

- First login and branch selection are online-only.
- Offline selling requires a cached open shift owned by the current cashier.
- The pilot does not open a new shift offline.
- The production pilot must add an explicit local-authorization expiry; the current development build persists the signed-in session so short network outages do not stop a sale.
- Closing a shift locally marks it pending; the server close request runs only after the order outbox for that shift is empty.
- User/branch revocation is applied on the next successful contact with the API.

## Android packaging

- Capacitor packages the dedicated cashier build and embedded static assets.
- The API base URL is injected at build time and is never hard-coded in cashier modules.
- Development builds use a development application ID and local/staging API.
- Production uses a stable application ID, a protected signing key, and HTTPS only.
- The PWA service worker is disabled inside the native build; explicit local repositories own cached API data.
- Native integrations are introduced behind adapters for network state, secure credentials, app lifecycle, screen wake lock, and ESC/POS printing.

The Android project can be scaffolded before a production domain exists. DNS, TLS, final API URL, final application ID registration, and release distribution remain release gates.

## Pilot acceptance tests

1. Bootstrap online, then sell while airplane mode is enabled.
2. Persist 100 paid offline orders and reload the app.
3. Restart the device and verify that all 100 orders remain queued.
4. Restore connectivity and receive one acknowledgement for every order.
5. Replay the full batch and verify that order, payment, queue, and stock totals do not change.
6. Drop the response after the server commits and verify safe retry.
7. Reject one row in a multi-order batch and verify that other rows still synchronize.
8. Confirm branch and cashier attribution for BKK-01 and an explicitly assigned test branch.
9. Confirm that store users cannot read central RAW/READY stock.
10. Upgrade the Android build without clearing the outbox.

## Release gates waiting for the domain

- Production DNS and trusted TLS certificate.
- HTTPS health, login, bootstrap, and synchronization smoke tests.
- Production API origin/CORS policy for the Android runtime.
- Final Android application ID and developer registration.
- Release keystore backup and signed APK/AAB.
- Physical-device UAT with the selected printer model.
