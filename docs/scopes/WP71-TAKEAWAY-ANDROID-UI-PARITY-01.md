# WP71 — Takeaway Android UI Parity

Date: 2026-09-27

Environment: Local/UAT only

Production: HOLD / unchanged

Version: `1.1.0-uat.1` (`versionCode 10100`)

## Objective

Package the approved Foodchainservice Takeaway UI in the existing Capacitor
Android application without enabling Takeaway transaction writes or changing
the Server release gates.

## Changes

- Align the Android UAT application name with Foodchainservice Takeaway.
- Route a successful native login to `/takeaway` instead of the shared ERP
  admin route.
- Use the current Takeaway visual language on the native login screen.
- Hide the shared ERP escape link inside the dedicated native application.
- Add Android safe-area, dynamic viewport and touch-target behavior while
  retaining text selection in form controls.
- Keep the web application and Android application on one React UI source.

## Release boundary

- `1.1.0-uat.1` is an internal UAT build. It is not a Production release.
- The future Production candidate may use `1.1.0` only after physical-device
  acceptance and owner sign-off.
- Takeaway write gates, payment/provider settings, Chambo cutover and
  Production flags remain unchanged.

## Required verification

- Frontend TypeScript and Android web build.
- Capacitor sync and Android debug compile/lint/unit tests.
- Install on a physical Android tablet or phone.
- Check portrait/landscape, soft keyboard, Android Back, restart/session
  recovery, Bluetooth permissions, Thai receipt, paper-out and reconnect.
- Confirm every transaction control still mirrors the Server-authoritative
  Dark Launch/HOLD state.

## Local verification result

- Frontend TypeScript: PASS.
- Android UAT web build and Capacitor sync: PASS; 4,259 modules and three
  Capacitor plugins.
- Takeaway browser regression: PASS, 6/6.
- Android debug unit tests, lint and `assembleDebug`: PASS.
- APK identity: `com.foodchainservice.takeaway.uat`.
- APK label/version: `Foodchainservice Takeaway UAT` / `1.1.0-uat.1`.
- Minimum/target SDK: 23 / 35.
- Debug signature verification: PASS using APK signature schemes v1 and v2.
- UAT artifact:
  `releases/uat/foodchainservice-takeaway-1.1.0-uat.1.apk`.
- SHA-256:
  `a11b7f1c2e26006cf4cad1dac4e8ff0070850e1d5b500f875ef0df140f5a0a59`.

Physical Android installation, orientation, session recovery, Bluetooth
printer and network interruption remain pending and must not be inferred from
the local build result.

## WP72 follow-up build note

The later Sketch Biz multi-company login and public QR-origin changes pass the
TypeScript check, Android UAT web build and Capacitor sync. A replacement APK
must be assembled before distribution because the APK hash above predates those
two changes. This Mac currently has no Java runtime, so the replacement APK and
its new SHA-256 remain pending; the older artifact must not be treated as the
WP72 candidate.
