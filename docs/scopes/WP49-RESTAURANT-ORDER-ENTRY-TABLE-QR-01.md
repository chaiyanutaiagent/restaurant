# WP49 — Restaurant Order Entry, Table and QR Experience

Date: 2026-09-21  
Environment: Local and UAT only  
Production: unchanged; deployment and feature activation are not authorized

## Objective

Connect the approved Restaurant touch-first design to the existing server-authoritative dining flow without changing the established WP43–WP48 business contracts.

The primary operator journey is:

```text
Table map → Open table/session → Session QR → Staff order entry
→ Category/menu selection → Quick options/note → Server price validation → Kitchen tickets
```

## Implemented scope

### Staff order composer

- Replace the small legacy Staff order sheet with a full-screen desktop/iPad landscape composer.
- Keep category rail, product grid and order cart visible together at 1024×768 and wider.
- Use 44px minimum interactive targets, a 64px primary Kitchen action, clear focus states and text/icon status cues.
- Support search, duplicate-category grouping, image fallback, quantities, removal and multiple lines of the same product with different notes.
- Reuse the approved quick-option vocabulary. Quick options remain plain `special_request` evidence and do not claim to be priced modifiers.
- Show Loading, Empty, No results, Error and Offline states through the shared state language.

### Server-authoritative boundary

- Load the Staff menu through `catalog_scope=restaurant_menu` using the signed Company/Brand/Branch context.
- Request only active, saleable `menu_item` products.
- Send `expected_unit_price`, `cart_version` and a stable idempotency key with the Staff order.
- The Server remains authoritative for price, tax, availability and Kitchen ticket creation; stale price or context conflicts fail closed.

### Table and QR workspace

- Preserve the existing session-scoped QR lifecycle and four table states.
- Keep the four-zone dataset and operational counts visible.
- Raise table management, QR, Open table, Order, Checkout and Close controls to the POS touch baseline.
- Preserve permission and branch scoping from the existing Server routes.

## Acceptance criteria

1. Cashier/Service Staff can open an active table session and obtain a session-scoped QR without exposing a permanent table token.
2. Staff order entry shows only the Restaurant catalogue allowed by the signed context.
3. Category labels are unique after normalized grouping and every product under legacy duplicate category IDs remains reachable.
4. The same product can be added as separate lines when its `special_request` differs.
5. Sending an order uses one stable idempotency key across retry and the Server recalculates price before creating Kitchen tickets.
6. Offline state blocks the Kitchen submit action and does not claim that an order was sent.
7. Desktop 1440×900 and tablet landscape 1024×768 have no page-level horizontal overflow; visible controls are at least 44×44px.
8. Existing Customer QR, KDS, cancellation/waste, checkout and audit outcomes do not regress.

## Explicit non-actions

- No schema migration.
- No priced modifier group, recipe surcharge or modifier tax contract.
- No Reservation, Waitlist, Delivery, Split bill or Table transfer activation.
- No Production deployment or Production flag change.
- No Takeaway/Central Kitchen Production transaction activation.
- No edit or commit under `docs/ux-ui/`.

## Rollback

- Revert the WP49 frontend candidate and restore the WP48 UAT frontend image.
- No database rollback is required.
- Existing session, order, QR and Kitchen data remain compatible because no API or schema contract is removed.
