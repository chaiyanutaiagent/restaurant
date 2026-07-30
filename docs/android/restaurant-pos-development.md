# Restaurant POS POS Android — Development and Build Guide

## Current artifact

The Android shell is generated under `frontend/android` with:

- Application ID: `com.chaiyanutaiagent.restaurant`
- Minimum SDK: 23 (Android 6)
- Target SDK: 35
- Capacitor: 7
- Cleartext HTTP: disabled
- Android app backup: disabled

The generated debug APK is intentionally ignored by Git:

`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

It proves that the native project compiles. Until `.env.android` contains a real HTTPS API origin, the APK is not a connected production/pilot build.

## One-time local toolchain

```bash
brew install openjdk@21 android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
sdkmanager --licenses
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

Create the ignored `frontend/android/local.properties` file if Capacitor/Gradle did not create it:

```properties
sdk.dir=/opt/homebrew/share/android-commandlinetools
```

## Configure the API after the domain is ready

Copy `frontend/.env.android.example` to `frontend/.env.android` and replace the placeholder with the HTTPS origin only:

```dotenv
VITE_API_BASE_URL=https://pos.example.com
VITE_COMPANY_ID=1b8a1818-44d6-4d5f-9d22-e5e17b23c081
```

Do not append `/api/v1`; the app adds it. Add `https://localhost` to the backend production `CORS_ORIGINS` because that is the secure Capacitor WebView origin. The server API origin itself must have a trusted certificate.

## Build

```bash
cd frontend
npm ci
npm run type-check
npm run android:apk
```

The Android build disables the PWA service worker. IndexedDB and the restaurant
outbox own offline data inside the app.

Install a debug build on a USB-connected device:

```bash
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

## Required device test

1. Install the APK and log in online as a branch employee.
2. Confirm the correct branch, cashier, menu, shift, and store location.
3. Sell one cash order and one cashier-confirmed PromptPay order online.
4. Enable airplane mode while keeping the app open.
5. Sell at least three orders; confirm offline queue labels, local slips, and the `รอส่ง` count.
6. Force-close and reopen the app; confirm queued orders remain.
7. Restore connectivity; confirm the pending count returns to zero.
8. Confirm each local order created exactly one server sale/session and stock was posted once.
9. Create a controlled price/shift conflict and confirm it appears as `ต้องตรวจสอบ` without deleting the local order.
10. Confirm logout and shift close are blocked while pending/review rows exist.

## Release gates

- Final domain/TLS and Android API environment.
- Final icon, splash screen, app name approval, and versioning.
- Secure release keystore stored outside Git with a tested recovery backup.
- Signed release APK/AAB and developer/distribution registration.
- ESC/POS printer model selection and physical print tests.
- Decide whether app-terminated background sync is required for the pilot; if yes, add a native Room/WorkManager outbox adapter.
