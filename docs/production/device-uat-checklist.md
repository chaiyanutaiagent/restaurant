# Phase 5 Physical Device UAT Checklist

Use this checklist only when the real hardware is available. Browser emulation is useful pre-flight evidence but cannot validate the camera, touch hardware, kiosk behavior, local network, printer, power recovery, or device-management policy.

Current status: `physical_device_uat: pending`

## Test record

```text
release_commit:
environment:
base_url:
test_date:
business_owner:
technical_operator:
counter_device_model_os_browser:
kitchen_device_model_os_browser:
pickup_device_model_os_browser:
printer_model_connection:
network_name_or_test_profile:
evidence_location:
```

Do not record Wi-Fi passwords, application passwords, pairing PINs, tokens, QR secrets, or customer payment data.

## Preconditions

- [ ] The release commit and UAT environment are identified and isolated from live customer transactions unless production UAT has been explicitly approved.
- [ ] Test users, branch, menu, stock, payment method, table, and clearly marked UAT orders are prepared.
- [ ] Counter, kitchen, pickup display, Samsung Galaxy Tab A11 LTE or actual target tablet, camera, charger, stand, printer, and spare network path are available.
- [ ] An operator can revoke device credentials and clean up test data according to policy.
- [ ] Screenshot/photo/log evidence has an approved storage location outside Git.

## Pairing and device identity

- [ ] Pair each intended role using the one-time PIN or QR path and verify the displayed Company/Brand/Branch/device scope.
- [ ] Confirm a PIN cannot be reused after successful pairing or expiration.
- [ ] Reload, close/reopen the browser or installed app, and restart the device; confirm the intended session persists without exposing credentials.
- [ ] Confirm a counter credential cannot access kitchen-only or Platform Owner functions outside its scope.
- [ ] Revoke one UAT device, confirm its next protected request is denied, and pair it again with a new credential.

## Display and interaction matrix

For every target device, test portrait and supported landscape orientation where applicable.

- [ ] No horizontal clipping or hidden primary action at the supported zoom/font-size setting.
- [ ] Touch targets, scrolling, dialogs, numeric input, on-screen keyboard, and back navigation work without trapping the operator.
- [ ] Thai product names, notes, prices, totals, table labels, and status text are legible.
- [ ] Camera opens and scans the table QR under normal restaurant lighting.
- [ ] Refresh and power/network recovery do not duplicate an order or lose the visible workflow state.

## Dine-in flow

- [ ] Scan the table QR and verify the correct restaurant and table.
- [ ] Add products, option/quantity, and the note `DEVICE-UAT`; submit once.
- [ ] Verify the table map and kitchen queue show one matching order.
- [ ] Move the kitchen job through start, ready, and served; verify the customer status updates.
- [ ] Request the bill, collect an approved test payment, and confirm receipt/view output.
- [ ] Reconcile order, payment, stock/recipe movement, accounting journal/outbox, branch report, and central report.

## Takeaway flow

- [ ] Create a clearly marked takeaway order and verify that it has no dine-in table dependency.
- [ ] Move it through kitchen and pickup states and verify the pickup display/queue.
- [ ] Complete the approved test payment and reconcile the same downstream records as dine-in.

## Connectivity and retry behavior

- [ ] With a prepared unpaid UAT order, disconnect the counter device and confirm the UI communicates offline state clearly.
- [ ] Submit/retry only according to the supported offline workflow, restore connectivity, and verify exactly one canonical sale/payment.
- [ ] Interrupt connectivity after submission but before acknowledgement, retry, and verify no duplicate sale, payment, kitchen job, stock movement, journal, or outbox event.
- [ ] Confirm the application recovers after Wi-Fi to LTE/fallback switching where the target deployment supports it.

## Peripheral and operations checks

- [ ] Print a UAT receipt and kitchen ticket; verify Thai text, totals, identifiers, paper width, cut/feed, and reprint behavior.
- [ ] Verify a disconnected/out-of-paper printer produces an actionable message and does not duplicate the transaction when retried.
- [ ] Confirm screen timeout, charging, kiosk/full-screen behavior, notification volume, and shift handover meet restaurant operations.
- [ ] Review browser console/network evidence when accessible and record any page error, CSP violation, failed request, or HTTP 5xx.

## Completion record

```text
dine_in_result: pending
takeaway_result: pending
pairing_revocation_result: pending
offline_retry_result: pending
printer_result: pending
reconciliation_result: pending
business_owner_decision: pending
Platform Owner completion approval: pending
notes:
```

A failed or untested item remains pending. Do not infer approval from automated Chromium evidence, and do not begin Phase 6 until the Restaurant Completion Gate and Platform Owner completion approval are recorded.
