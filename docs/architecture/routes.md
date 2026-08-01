# Route Plan

## Module Launcher

- `/` - module launcher
- `/store` - public storefront

## ERP Admin

- `/admin` - canonical ERP Admin entry
- `/erp` - ERP alias, redirects to `/admin`
- `/dashboard` - legacy ERP dashboard kept during migration
- `/integrations` - API keys, webhooks, and external orders

## POS

- `/pos` - cashier workspace
- `/pos/admin` - POS Admin hub

Planned POS Admin pages:

- `/pos/admin/settings`
- `/pos/admin/shifts`
- `/pos/admin/payment-methods`
- `/pos/admin/receipts`
- `/pos/admin/reports`

## Restaurant

- `/restaurant` - Restaurant workspace
- `/restaurant/admin` - Restaurant Admin hub
- `/restaurant/tables`
- `/restaurant/orders`
- `/restaurant/kitchen`
- `/restaurant/pickup`
- `/restaurant/recipes`
- `/restaurant/qr`
- `/restaurant/settings`
- `/restaurant/reports/ingredients`
- `/restaurant/wap` - staff paid-first WAP order entry inside Restaurant workspace

## Restaurant WAP

- `/restaurant` - Restaurant shop alias, redirects to `/restaurant/orders`
- `/restaurant/orders` - dedicated paid-first staff order app for `ระบบร้านอาหาร`
- `/restaurant/kitchen` - Restaurant kitchen display alias
- `/restaurant/pickup` - Restaurant pickup display alias

## Public Restaurant Ordering

- `/menu/:token` - dine-in session QR menu
- `/order/:token` - quick-service QR menu

## Phase 3 Device APIs

- `GET/POST /api/v1/system/devices` - scoped device list and registration
- `POST /api/v1/system/devices/:id/pairing-code` - rotate one-time pairing PIN/QR
- `POST /api/v1/system/devices/:id/revoke` - revoke a device and invalidate its token
- `POST /api/v1/device-auth/pair` - exchange a one-time credential for a device token
- `POST /api/v1/device-auth/renew` - exchange the persistent device refresh credential for a new access token
- `GET /api/v1/device-auth/me` - validate the live registry and return server-owned device context
- `GET /api/v1/device-workspaces/counter/bootstrap` - validate a Counter device and return its locked Branch plus staff-login gate
- `GET/PATCH /api/v1/device-workspaces/kitchen/...` - Station-locked Kitchen ticket workspace
- `GET/POST /api/v1/device-workspaces/pickup/...` - Branch-locked Pickup queue workspace

Dedicated browser routes are `/counter`, `/counter/orders`, `/kitchen`, and `/pickup`; `/device/pair` exchanges the
one-time pairing credential, while `/devices` is the scoped Manager console. Existing
`/restaurant/kitchen` and `/restaurant/pickup` user-session routes remain available.

The tablet hydrates its device session from native secure storage before route guards run and renews access
on app open. A temporary network failure retains the paired state; an expired access token shows a reconnect
gate instead of sending the operator back to Pair. Clearing app/site data or uninstalling intentionally removes
the local credential and requires a new Manager-authorized Pair.

On `/counter/orders`, Restaurant menu bootstrap receives separate staff and Counter-device credentials and
opens the staff-owned shift when needed. `POST /api/v1/restaurant/wap/staff-shift/handover` requires both
credentials, validates the same Company/Branch, records the counted cash plus staff/device audit, and closes
the outgoing shift. The frontend then clears only the staff session while retaining the paired device for the
next operator. Generic `/pos` shift open/close also records staff and optional Counter-device evidence.

## Migration Rule

Keep legacy routes working while new canonical routes are introduced. Prefer redirects first, then move screens when each module admin is fully split.
