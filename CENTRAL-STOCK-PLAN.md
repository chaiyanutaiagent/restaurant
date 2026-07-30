# Central Stock Plan

Last updated: 2026-07-10

## Context

Work completed today focused on Restaurant central stock and production:

- `/central/restaurant/stock`
- `/central/restaurant/production`
- brand-specific APIs under `/api/v1/restaurant/central/{brand_slug}/...`

The flow is useful and should be lifted into a reusable central stock module so the main central office can manage stock across all brands, not only Restaurant.

## Current Restaurant Features Already Built

- Central stock page for Restaurant.
- Raw material list with image, SKU, category, unit, cost, min stock, on-hand, reserved, available, and status.
- Category filter and low/zero stock filter.
- Receive stock into Restaurant central location.
- Add/edit raw materials from the stock page.
- Add/edit categories and units from stock settings.
- View stock movement history per raw material.
- Start a stock count session for Restaurant central location.
- Production page compares required ingredients with central stock.
- Production complete button:
  - issues raw materials from central stock
  - receives produced goods into central stock
  - records movements with `central_production` reference.

## Goal

Add a main central stock experience that reuses the Restaurant stock flow:

- `/central/stock`
- `/central/production`
- optional `/central/settings/stock`

Restaurant routes should remain available as brand-filtered shortcuts.

## Proposed Routes

### `/central/stock`

Central stock across all brands.

Requirements:

- Brand selector:
  - All brands
  - Restaurant
  - Future brands
- Location selector:
  - central stock location
  - brand-specific central locations
- Summary cards:
  - raw material count
  - category count
  - low stock
  - zero stock
  - stock value
- Table:
  - image
  - product name
  - SKU
  - brand
  - category
  - unit
  - on hand
  - reserved
  - available
  - min stock
  - cost/unit
  - status
- Actions:
  - receive stock
  - add/edit raw material
  - movement history
  - stock count
  - category/unit settings

### `/central/production`

Production planning across all brands.

Requirements:

- Brand selector.
- Date range and status filters.
- Production output list.
- Required ingredient list.
- Compare against selected central stock location.
- Show shortages.
- Complete production:
  - issue ingredients
  - receive produced products
  - reference should include brand/date/filter context.

### `/central/settings/stock`

Optional later split-out page if the stock page settings modal becomes too large.

Requirements:

- Categories.
- Units.
- Central stock locations.
- Default min/target/reorder configuration.
- Brand to central branch/location mapping.

## Backend Plan

### Refactor Brand-Specific Logic Into Services

Move reusable logic out of router handlers into service helpers.

Suggested service functions:

- `get_central_stock_context(company_id, brand_slug=None, location_id=None)`
- `list_central_raw_materials(company_id, brand_id=None)`
- `build_central_production_summary(company_id, brand_id=None, date_from=None, date_to=None, status=None)`
- `build_central_production_ingredients(company_id, brand_id=None, date_from=None, date_to=None, status=None)`
- `complete_central_production(company_id, user_id, location_id, inputs, outputs, reference_context)`

### New API Endpoints

Add generic central endpoints:

- `GET /api/v1/restaurant/central/stock-context`
- `GET /api/v1/restaurant/central/recipe-products?brand_id=&product_type=raw_material`
- `GET /api/v1/restaurant/central/production-summary?brand_id=&date_from=&date_to=&status=`
- `GET /api/v1/restaurant/central/production-ingredients?brand_id=&date_from=&date_to=&status=`
- `POST /api/v1/restaurant/central/production-complete`

Keep existing Restaurant/brand routes:

- `/api/v1/restaurant/central/{brand_slug}/production-summary`
- `/api/v1/restaurant/central/{brand_slug}/production-ingredients`
- `/api/v1/restaurant/central/{brand_slug}/production-complete`

Those can call the same service logic with `brand_slug`.

### Stock Location Rules

- For a brand-specific page, default to `brand.central_location_id`.
- For `/central/stock`, allow:
  - selected central location
  - all central locations if reporting only
- For production complete, require one explicit `location_id`.

### Data Safety

- Never complete production if it would make stock negative.
- Production complete should use one transaction.
- Movement references should be structured enough for audit:
  - `reference_type = central_production`
  - `reference_id = brand/date/status/location` or a generated production batch id later.

## Frontend Plan

### Extract Reusable Components

Current page:

- `frontend/src/pages/restaurant/RestaurantCentralStockPage.tsx`

Extract reusable parts:

- `CentralStockPage`
- `CentralStockSummaryCards`
- `CentralStockReceivePanel`
- `IngredientEditorModal`
- `StockSettingsModal`
- `StockMovementModal`
- `CentralProductionPage`

### Route Behavior

`/central/restaurant/stock`:

- preselect brand `restaurant`
- hide or lock brand selector

`/central/stock`:

- show brand selector
- default to all brands or first central brand

`/central/restaurant/production`:

- preselect brand `restaurant`

`/central/production`:

- show brand selector
- allow all brands only for planning/reporting
- require one brand or clear grouping before production complete

## Implementation Phases

### Phase 1: Central Stock Page

1. Create generic `/central/stock` route.
2. Reuse Restaurant stock page component with optional `brandSlug`.
3. Add brand selector.
4. Add location selector.
5. Support all-brand raw material list.
6. Keep Restaurant route working unchanged.

### Phase 2: Settings Reuse

1. Keep category/unit settings shared.
2. Add central location settings or link to existing stock location page.
3. Add brand-to-location mapping if not enough through existing brand transfer config.

### Phase 3: Central Production Page

1. Create `/central/production` route.
2. Reuse production summary/ingredients tables.
3. Add brand selector.
4. Keep production complete brand-scoped at first.
5. Later support multi-brand production batches if business needs it.

### Phase 4: Better Production Batch Records

Current production complete writes stock movements only. Later add a real production batch table:

- batch number
- brand_id
- location_id
- date range
- status
- produced items
- consumed ingredients
- completed_by
- completed_at

This will make reports and undo/reversal easier.

## Recommended Next Session Start

1. Read this file.
2. Confirm latest server/local state:

```bash
git status --short
git log -3 --oneline
git remote -v
```

3. Start with Phase 1:

- add route `/central/stock`
- refactor `RestaurantCentralStockPage` so it can accept generic central mode
- add brand/location selectors
- build and deploy

## Relevant Files

- `frontend/src/pages/restaurant/RestaurantCentralStockPage.tsx`
- `frontend/src/pages/restaurant/RestaurantCentralProductionPage.tsx`
- `frontend/src/lib/wapApi.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/layout/RestaurantShell.tsx`
- `backend/app/routers/restaurant.py`
- `backend/app/routers/products.py`
- `backend/app/services/stock_service.py`
- `backend/app/schemas/restaurant.py`
- `backend/app/services/recipe_service.py`
- `backend/app/services/product_service.py`
