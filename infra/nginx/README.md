# Nginx Infrastructure

Production Nginx configuration lives in `nginx/conf.d/`:

- `default.prod.conf`: HTTP mode for first boot and internal verification.
- `default.prod.https.template.conf`: HTTPS template used after host certificates exist.

Nginx proxies `/api/`, `/webhooks/`, `/uploads/`, and `/health*` to the FastAPI
backend, and proxies `/` to the React frontend.
