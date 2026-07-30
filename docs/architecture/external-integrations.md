# External Integrations

Restaurant POS should connect to other systems through API keys, public APIs, incoming webhooks, and outbound webhooks.

## Source Names

Every external system should use a stable source name:

- `poolproject`
- `blifehealthy`
- `marketplace_x`

Allowed format: lowercase letters, numbers, underscores, and hyphens, 3-50 characters.

External orders are idempotent by:

```text
company_id + source + external_order_id
```

## Public API

Base path:

```text
/api/public/v1
```

Authentication:

```text
X-API-Key: erppos_...
```

Order ingestion:

```text
POST /api/public/v1/orders?source=poolproject
GET  /api/public/v1/orders/{external_order_id}?source=poolproject
```

Product and stock reads:

```text
GET /api/public/v1/products
GET /api/public/v1/products/{sku}
GET /api/public/v1/stock/{sku}
```

## Incoming Webhooks

Generic order webhook:

```text
POST /webhooks/{source}/orders
X-ERP-Signature: sha256=<hmac>
```

Legacy header support remains:

```text
X-Blife-Signature: sha256=<hmac>
```

## Payload Contract

```json
{
  "external_order_id": "POOL-20260609-001",
  "customer_name": "Customer Name",
  "customer_phone": "0800000000",
  "customer_email": "customer@example.com",
  "customer_address": "Delivery address",
  "items": [
    {
      "sku": "SKU-001",
      "qty": 1,
      "unit_price": "100.00"
    }
  ],
  "total_amount": "100.00",
  "payment_method": "transfer",
  "payment_status": "paid",
  "notes": "Optional note"
}
```

## Outbound Webhooks

Restaurant POS can send configured events to external systems:

- `order.received`
- `sale.created`
- `stock.low`
- `shipment.created`
- `shipment.status_updated`

## Poolproject Preparation

When connecting `poolproject`, create an API key with scoped access and use:

```text
source=poolproject
```

Do not share database tables directly. Keep Restaurant POS as the transaction and operation system, and synchronize through the integration layer.
