# Restaurant POS Public Domain Setup

This project does not include a production domain, server address, DNS account,
Cloudflare account, tunnel token, or company identifier from the source system.
Choose new values for this deployment and keep secrets outside Git.

## Choose the public origin

Use a dedicated HTTPS hostname, for example:

```text
https://pos.example.com
```

Set matching values in the ignored `.env.production` file:

```dotenv
SERVER_NAME=pos.example.com
PUBLIC_BASE_URL=https://pos.example.com
CORS_ORIGINS=["https://pos.example.com","https://localhost"]
```

Replace `example.com` with the new domain. `https://localhost` is required only
when the Capacitor Android app connects to this backend.

## Cloudflare Tunnel

1. Add the new domain to the intended Cloudflare account.
2. Create a new tunnel for this project.
3. Route the chosen hostname to `http://nginx:80`.
4. Store the tunnel token in the ignored
   `.secrets/cloudflare-tunnel-token` file on the production host.
5. Run:

```sh
./scripts/deploy-production-cloudflare.sh .env.production
```

The tunnel token is a secret. Do not commit it, paste it into issue text, or
reuse a token from another project.

## Android configuration

Copy `frontend/.env.android.example` to the ignored
`frontend/.env.android` file:

```dotenv
VITE_API_BASE_URL=https://pos.example.com
VITE_COMPANY_ID=1b8a1818-44d6-4d5f-9d22-e5e17b23c081
```

Do not append `/api/v1`.

## Verification

After DNS and the tunnel are healthy:

```sh
curl -I https://pos.example.com/health
curl https://pos.example.com/health/ready
COMPOSE_PROFILES=cloudflare PRODUCTION_STATUS_BASE_URL=https://pos.example.com ./scripts/check-production-status.sh
PRODUCTION_SMOKE_BASE_URL=https://pos.example.com ./scripts/smoke-production.sh .env.production
```

Run login, menu, branch, shift, online-sale, offline-sync, stock-posting, backup,
and restore checks before go-live.
