# Docker Infrastructure

Production Docker entrypoints remain at the repository root so existing deployment
automation can run without path changes:

- `docker-compose.prod.yml`: production stack for Ubuntu VPS.
- `docker-compose.yml`: local/development stack.
- `backend/Dockerfile`, `frontend/Dockerfile`, `nginx/Dockerfile.prod`: image builds.

The production stack runs `frontend`, `backend`, `postgres`, `redis`, and `nginx`
with named volumes for `postgres_data`, `redis_data`, and `uploads`.
