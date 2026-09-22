# WP54 — Restaurant Counter Readiness and Physical-UAT Shell

Date: 2026-09-22
Scope: **Local/UAT only**
Production: **NO-GO / unchanged**

## Objective

Turn the existing Physical UAT evidence contract into an operator-ready Counter Readiness gate while
preserving the rule that Browser checks and device `last_seen` never substitute for real hardware
evidence.

## Implementation

- UAT-only header with explicit Restaurant Pilot state and no Production activation action.
- Overall gate states for passed evidence, physical tests pending, failed checks and required blockers.
- Automatic checks display their source, timestamp and safe evidence snapshot.
- Manual checks display required status, tester/time, evidence reference, note and defect fields.
- Pass requires evidence; Fail requires evidence, defect ID and severity.
- N/A is exposed only for Cash drawer and still requires a Manager-approved reason.
- Direct workspace links help the operator start Product barcode, Table QR, POS, KDS, Takeaway and
  Offline Sync tests without marking them passed automatically.
- Release/Counter/OS/Browser/Printer/Network evidence snapshot remains immutable after session creation.
- Sign-off remains blocked by incomplete checks or P0/P1 defects and preserves maker-checker separation.
- Read-only users can review evidence but cannot record or sign off results.

## Existing server controls preserved

- UAT environment flag and Production validation.
- Company/Branch scope and paired-Counter requirement.
- Automatic queue, release, API, shift and pairing checks.
- Evidence secret filtering and immutable approved sessions.
- Separate submitter, Technical checker and Business checker audit trail.

## Boundary

This work improves the readiness shell and evidence workflow. It does not claim that a printer,
cash drawer, camera, payment terminal, network interruption or multi-device test passed. Only the
tester using the actual target device may record that evidence.

