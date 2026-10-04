#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

assert_contains() {
  pattern=$1
  file=$2
  if ! grep -Fq "$pattern" "$ROOT_DIR/$file"; then
    echo "FAIL: expected '$pattern' in $file" >&2
    exit 1
  fi
}

assert_absent() {
  pattern=$1
  path=$2
  if grep -R -Fq "$pattern" "$ROOT_DIR/$path"; then
    echo "FAIL: found legacy identity '$pattern' in $path" >&2
    exit 1
  fi
}

assert_contains 'appId: "com.foodchainservice.takeaway"' frontend/capacitor.config.ts
assert_contains 'applicationId "com.foodchainservice.takeaway"' frontend/android/app/build.gradle
assert_contains 'applicationIdSuffix ".uat"' frontend/android/app/build.gradle
assert_contains 'refusing to create an unsigned release' frontend/android/app/build.gradle
assert_contains 'android.permission.BLUETOOTH_CONNECT' frontend/android/app/src/main/AndroidManifest.xml
assert_contains 'android.permission.BLUETOOTH_SCAN' frontend/android/app/src/main/AndroidManifest.xml
assert_contains 'name = "TakeawayPrinter"' frontend/android/app/src/main/java/com/foodchainservice/takeaway/TakeawayPrinterPlugin.java
assert_contains 'com.foodchainservice.takeaway' docs/contracts/takeaway-release-manifest-v1.schema.json
assert_absent 'com.chaiyanutaiagent.restaurant' frontend/android/app/src

node --check "$ROOT_DIR/scripts/create-takeaway-release-manifest.mjs"
node --check "$ROOT_DIR/scripts/verify-takeaway-release-manifest.mjs"

echo "PASS: Takeaway Android identity, Bluetooth permission, signing gate and update contract"
