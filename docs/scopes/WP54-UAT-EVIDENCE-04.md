# WP54 UAT Evidence — Restaurant Counter Readiness

Date: 2026-09-22  
Environment: UAT only  
Production: unchanged and not authorized

## Immutable candidate

| Item | Identity |
|---|---|
| Source commit | `525163f` |
| UAT archive | `/tmp/restaurant-wp54-525163f.tar.gz` |
| Archive SHA-256 | `dfa902ab5e7c7e372320ed7aee35905ced4403748023227ccd566b1c98b2ceb9` |
| Backend image | `restaurant-pos-backend:wp54-525163f` |
| Backend image ID | `sha256:a410184ebe6f2f5665766dbe8dbc4223e18938019052bd4cba55a1289cca9aad` |
| Frontend image | `restaurant-pos-frontend:wp54-525163f` |
| Frontend image ID | `sha256:c6e884592211a6bf7f9afe27b0d064d99550645418b0d485d33c8eb1a121cf32` |
| UAT route | `https://uat-pos.foodchainservice.com/devices/uat-readiness` |

## Engineering evidence

- WP52–WP54 focused regression: 17 tests passed.
- Frontend type-check: passed.
- Frontend production build: passed; only the pre-existing bundle-size advisory remained.
- Health checks after restore: `/`, `/devices/uat-readiness`, `/pos/offline-sync`, `/health`, and `/health/ready` returned HTTP 200.
- Tablet visual inspection at 1024 × 768 showed no horizontal overflow and retained the complete operator workflow.

## UAT session evidence

The session was created with the paired UAT Counter and an explicit automated-browser preflight label. No browser capability was recorded as physical evidence.

| Result | Count |
|---|---:|
| Automatic checks passed | 5 |
| Automatic checks failed | 0 |
| Physical/manual checks pending | 15 |
| Required blockers | 15 |

The final submit action remained disabled with `ยังส่งไม่ได้ · ค้าง 15`. Printer, cash drawer, PromptPay, controlled network loss/reconnect, multi-device concurrency, reconciliation, and recovery therefore remain unverified until a tester supplies real evidence.

## Hard-gate finding and resolution

The first UAT run correctly failed release identity: the page expected `525163f` while the running backend reported `b329d2c`. Engineering did not bypass the gate. The UAT backend was rebuilt from the same `525163f` source and the release identity was aligned. A refresh then produced five automatic passes and zero automatic failures.

No database schema, Production configuration, real provider, real tax document, or real business data was changed.

## Rollback and restore

- Rollback to the previous UAT pair completed in 8 seconds:
  - backend `restaurant-pos-backend:wp52-e4e3ad9`
  - frontend `restaurant-pos-frontend:wp53-ca3fb25`
- Restore to the immutable WP54 pair completed in 9 seconds.
- Nine transient UAT nginx 5xx responses occurred only during the deliberate backend restart windows.
- After restore, ten consecutive readiness requests passed and the following 15-second observation contained zero 5xx responses.

## Production identity check

Production identities were unchanged before and after the UAT operation:

- backend `restaurant-pos-backend:auth-a0fdccf` / `f6e08435721a`
- frontend `restaurant-pos-frontend:ui-e4200ca` / `857e0dbab1a2`
- nginx `restaurant-pos-nginx:unified-d528512` / `aea97e7f90f7`
- cloudflared `cloudflare/cloudflared:2026.7.0` / `ae6862f8a09f`
- postgres `postgres:15-alpine` / `3565e3fd72ad`
- redis `redis:7-alpine` / `76658d7ad2fd`

## Evidence conclusion

The Counter Readiness shell, fail-closed rules, immutable release identity, rollback, restore, Desktop/tablet presentation, and evidence model pass the WP54 engineering/UAT delivery gate. Physical hardware and controlled-network acceptance remain open operational release blockers; no physical pass or Production readiness is claimed.
