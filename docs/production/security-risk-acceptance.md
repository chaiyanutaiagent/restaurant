# Phase 5 Security Risk Decision

This is a decision record for an accountable security owner. It is not an automatic acceptance and does not replace fresh release-time audits, penetration testing, or compliance review.

```text
security_owner_decision: pending
decision_options: accept_for_release / mitigate_before_release / block_release
release_commit:
audit_date_utc:
security_owner:
decision_date_utc:
expiry_or_review_date:
ticket_or_evidence:
conditions:
```

## Reviewed dependency findings

The 1 August 2026 `P5-UAT-SECURITY-03` evidence recorded:

- Backend `pip-audit`: zero known vulnerabilities after the documented dependency upgrades.
- Frontend production audit: two high-severity package rows from one React Router RSC-mode Action advisory, `GHSA-qwww-vcr4-c8h2`.
- Execution-path review: this application uses declarative `BrowserRouter` in a static CSR bundle and has no React Router Actions, RSC, SSR, `RouterProvider`, or router server runtime. The production image contains nginx and static assets only.
- Frontend full audit: five package rows, three high and two moderate, including the production rows above and Vite/esbuild development-server findings. Vite and its Node toolchain are absent from the production nginx runtime.
- No critical npm finding was recorded.

These counts are historical evidence, not a waiver. Re-run both the production-only and full frontend audits plus the backend audit against the exact release commit. If advisory data, dependency versions, architecture, or runtime reachability changes, update this record before deciding.

Fresh frontend observation on 10 September 2026 while preparing `P5-POS-TABLET-UX-07`:

- `npm audit --omit=dev --audit-level=high` reported four package rows: three high and one low (`nanoid`, `postcss-selector-parser`, `react-router`/`react-router-dom`).
- The full `npm audit --audit-level=high` reported eleven package rows: seven high, three moderate, and one low. Additional findings are in the Capacitor/build/PWA toolchain (`@xmldom/xmldom`, `browserslist`, `esbuild`, `fast-uri`, and related dependency paths).
- No critical npm finding was reported. No dependency was auto-upgraded in the Tablet UX scope because a combined update includes build-tool and potential breaking-version risk.
- This refresh is not an acceptance. Production sign-off remains blocked on exact-release audit, reachability review, mitigation/acceptance, and the named security-owner decision.

## Other residual risks

- Uploaded images are publicly reachable by URL.
- Malware scanning, object storage, per-tenant quota, and lifecycle cleanup are not implemented.
- WeasyPrint can emit fontconfig cache warnings while PDF output succeeds.
- The physical-device CSP/browser path, printer path, and local-network behavior remain unverified until device UAT.
- Operator, monitoring destination, live DNS/TLS values, and production secret source require owner confirmation.

## Decision guidance

- `accept_for_release`: the owner agrees the documented conditions, compensating controls, scope, and review/expiry date are adequate for this release.
- `mitigate_before_release`: identify the required dependency/tooling or upload-control work, responsible owner, test evidence, and due date.
- `block_release`: do not deploy or sign the Restaurant Completion Gate until the blocker is resolved and re-reviewed.

```text
fresh_backend_audit_result:
fresh_frontend_production_audit_result:
fresh_frontend_full_audit_result:
architecture_reachability_unchanged: pending
upload_risk_decision: pending
device_csp_evidence: pending
required_mitigation:
mitigation_owner:
mitigation_due_date:
security_owner_signature_or_approved_record:
```

Only the named security owner may change `security_owner_decision` from `pending`. Link the approved decision from the final sign-off record; never paste confidential audit data or credentials into Git.
