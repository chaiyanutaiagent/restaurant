# Permission And Role Presets

Restaurant POS uses permission codes as the enforcement layer. Roles are company-scoped bundles of permissions.

## Permission Domains

- `system.*` - ERP core administration
- `inventory.*` - Product, stock, purchase, and transfer operations
- `accounting.*` - Accounting, payments, invoices, and e-tax
- `pos.*` - POS sales, shifts, refunds, discounts, and reports
- `fb.*` - Restaurant/F&B operations
- `brand.*` - Brand storefront apps, replenishment, and delivery receive
- `hr.*` - HR, attendance, and payroll

## Recommended Role Presets

### ERP Admin

For core platform administration.

Includes:

- Company and branch management
- User and role management
- Product and inventory administration
- Purchase and transfer access
- Accounting and payment visibility

### POS Manager

For store managers responsible for POS operations.

Includes:

- POS sales and sale history
- Void, refund, and discount override
- Open and close cashier shifts
- POS reports
- Product and stock visibility

### Cashier

For front-line POS users.

Includes:

- POS sale creation
- Standard discount application
- Open and close cashier shifts
- Product and stock visibility

### Store Cashier

For brand storefront users such as Restaurant branch staff.

Includes:

- Brand storefront order creation
- Brand storefront shift close
- Store replenishment request submission
- Delivery receive from central operations

### Restaurant Manager

For restaurant/F&B managers.

Includes:

- Menu and session visibility
- Table management
- Order management
- Kitchen management
- Recipe management
- F&B reports and settings
- Product and stock visibility

### Kitchen Staff

For kitchen display users.

Includes:

- F&B menu/session visibility
- Kitchen ticket status updates

### Integration Admin

For users managing external system connections such as `poolproject`.

Includes:

- API keys and webhook administration
- External order visibility
- External order fulfillment handoff

## Migration Rule

Keep existing role names working. Add presets as a starting point for new roles; do not rewrite existing company roles automatically unless explicitly requested.
