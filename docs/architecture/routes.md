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
- `GET /api/v1/device-auth/me` - validate the live registry and return server-owned device context

Dedicated Counter, Kitchen, and Pickup device workspace routes remain in the next Phase 3 Scope.

## Migration Rule

Keep legacy routes working while new canonical routes are introduced. Prefer redirects first, then move screens when each module admin is fully split.
