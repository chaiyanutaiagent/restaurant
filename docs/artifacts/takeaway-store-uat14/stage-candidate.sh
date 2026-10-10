#!/usr/bin/env bash
set -euo pipefail
release=/home/behappyaiagent/restaurant-uat-releases/takeaway-store-uat14-print-batch
downloads=/home/behappyaiagent/restaurant-uat-downloads/takeaway-store
expected_latest=026f7cb1d657660eabb8f604892607f66679fa683b9723a42800b9e56c2d926b
test "$(sha256sum "$downloads/latest.json" | cut -d' ' -f1)" = "$expected_latest"
test "$(sha256sum "$release/foodchainservice-takeaway-store-1.1.0-uat.14.apk" | cut -d' ' -f1)" = 34eabc30c9ba6d7ddab37905c9ff3fa68f36adcd73bfde7d1558934428feacec
# Hard links refuse an existing target. Never replace latest.json or another release.
test ! -e "$downloads/foodchainservice-takeaway-store-1.1.0-uat.14.apk"
test ! -e "$downloads/latest-uat.14.json"
chmod 444 "$release/foodchainservice-takeaway-store-1.1.0-uat.14.apk" "$release/latest-uat.14.json"
ln "$release/foodchainservice-takeaway-store-1.1.0-uat.14.apk" "$downloads/foodchainservice-takeaway-store-1.1.0-uat.14.apk"
ln "$release/latest-uat.14.json" "$downloads/latest-uat.14.json"
test "$(sha256sum "$downloads/latest.json" | cut -d' ' -f1)" = "$expected_latest"
echo 'PASS: versioned UAT14 artifacts staged only; latest.json unchanged on UAT13'
