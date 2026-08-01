# Module Boundaries

## ERP Admin

Route root: `/admin` with legacy `/dashboard`.

Owns:

- Company and branch settings
- Users, roles, and permissions
- Counter, Kitchen, and Pickup device registry and pairing lifecycle
- Product catalog and categories
- Inventory and stock movement
- Accounting, tax, purchase, logistics, and consolidated reports
- API keys and webhooks

## POS Module

Workspace route: `/pos`

Admin route: `/pos/admin`

Owns:

- Cashier shifts
- Sale orders
- Payments
- Receipts
- Refunds and voids
- POS reporting

Uses ERP data:

- Branches
- Products
- Prices
- Stock locations
- Tax and payment settings

## Restaurant Module

Workspace route: `/restaurant`

Admin route: `/restaurant/admin`

Owns:

- Dining tables
- Dining sessions
- Session QR tokens
- Customer QR ordering
- Kitchen tickets
- Pickup queue
- Recipes and ingredient usage
- F&B settings

Uses ERP data:

- Branches
- Products as menu items
- Inventory and raw materials
- Payments and sale checkout
- Branch/Station-bound device identity

## Integration Layer

Admin route: `/integrations`

Owns:

- API keys and scopes
- Webhook endpoints and deliveries
- External orders
- External source names such as `poolproject`
- Idempotency using `(company_id, source, external_order_id)`
