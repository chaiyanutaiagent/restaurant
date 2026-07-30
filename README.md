# Restaurant POS

## 1. Project overview

Restaurant operations and POS system for Thailand with multi-tenant, multi-branch,
offline-ready ordering, kitchen, recipes, inventory, and Docker-based deployment
for Ubuntu VPS environments.

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
