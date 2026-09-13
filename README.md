# Foodchainservice Platform

## 1. Project overview

Multi-business SaaS platform for Thailand with Company Admin, shared ERP and supply-chain
services, Restaurant POS, Retail POS, Takeaway POS, and a planned Hotel PMS module.
Restaurant and Takeaway operations are offline-aware and each operational domain is kept
behind an explicit database and permission boundary.

This repository starts from a clean source snapshot. It intentionally contains no
production database, secrets, brand-specific menu seed, receipt artwork, or
hard-coded restaurant brand.

## 2. Prerequisites

- Docker
- Docker Compose v2
- Node 20+
- Python 3.11+

## 3. Quick start

```bash
cp .env.example .env
docker compose up -d
# visit http://localhost:8081
```

## 4. Development notes

- Backend uses FastAPI, SQLAlchemy async, Alembic, Redis, and Celery.
- Frontend uses React, Vite, Zustand, React Query, Tailwind CSS, Dexie, and Workbox PWA support.
- Nginx proxies the React frontend and FastAPI backend through a single entrypoint.
- Docker development mode mounts the backend and frontend source trees for fast iteration.

## 5. Project structure overview

```text
restaurant/
├── backend/
├── frontend/
├── nginx/
├── docker-compose.yml
├── docker-compose.prod.yml
└── .env.example
```
