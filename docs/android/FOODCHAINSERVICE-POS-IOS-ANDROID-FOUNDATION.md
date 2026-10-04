# Foodchainservice POS for iOS and Android

อัปเดต 4 ตุลาคม 2026 จาก Takeaway UAT 8 ที่ commit `4e9575d` รอบนี้พัฒนา Android UAT candidate ให้เชื่อม Takeaway, Restaurant และ Retail ผ่านบัญชีที่เซิร์ฟเวอร์ตรวจสิทธิ์ โค้ดและ APK อยู่ในเครื่อง ยังไม่ใช่การเปิด Production และยังไม่ได้ deploy backend ใหม่

ตรวจ UAT แบบอ่านอย่างเดียวพบว่า `/api/v1/mobile-pos/context` ยังตอบ HTTP 404 ดังนั้น APK รุ่นนี้ยังเข้าใช้ UAT ไม่ได้จนกว่าจะ deploy backend ที่รองรับ ไม่มีการเปลี่ยนข้อมูล flags, hostname หรือ data source ของระบบที่ใช้อยู่

## สิ่งที่พัฒนาแล้ว

- แอปเดียวชื่อ Foodchainservice POS UAT รหัส `com.foodchainservice.pos.uat` แยกจาก Takeaway เดิม ไม่ทับการติดตั้งหรือข้อมูลค้างส่งเดิม
- เลือกผลิตภัณฑ์ กรอก Business Code บัญชีพนักงาน จุดขาย และเลือกเฉพาะสาขาที่มีสิทธิ์ ไม่ฝังบัญชีรหัสผ่าน tenant หรือ auto-login ใน APK
- Takeaway ใช้หน้าขาย เตรียมสินค้า สินค้า สต๊อก รับสินค้าส่วนกลาง กะ เครดิตและโอนสินค้าตามสิทธิ์เดิม รักษา token แบบ `takeaway_store` และข้อจำกัดเดิม
- Restaurant เชื่อมหน้าขาย โต๊ะและ QR ออร์เดอร์ รายละเอียดและชำระเงินโต๊ะ KDS และลูกค้า ผ่าน session แบบ `restaurant_pos`
- Retail เชื่อมหน้าขายและสแกนสินค้า พักบิล คืนสินค้า และกะ ผ่าน session แบบ `retail_pos` ไม่เปลี่ยน data source และไม่ปลดล็อกการขายออฟไลน์ที่เดิมไม่อนุญาต
- ทั้งสองระบบใช้กระบวนการขาย ราคา สิทธิ์อนุมัติ และรายการค้างของเว็บเดิม ไม่สร้างบัญชีธุรกรรมซ้ำ การเข้าได้ขึ้นกับสิทธิ์รายหน้า บัญชีที่มีเพียงสิทธิ์อ่านและไม่มีหน้าทำงานที่รองรับจะเริ่มที่หน้าอุปกรณ์
- หน้าต้อนรับรองรับโทรศัพท์และแท็บเล็ต ส่วนหน้าขายเต็มรูปแบบใช้ร่วมกับเว็บและยังต้องตรวจการจัดวางบน Android จริง โดยเฉพาะจอเล็ก
- เชื่อม Android Bluetooth ESC/POS เดิมสำหรับใบเสร็จที่รองรับ พร้อมเลือกเครื่องพิมพ์ที่จับคู่และปุ่มพิมพ์ทดสอบ จัดการการปฏิเสธหรือถอนสิทธิ์ Bluetooth โดยไม่ปิดแอป
- เพิ่ม Android system print dialog/PDF สำหรับเอกสาร HTML และ QR รอหน้าเอกสารโหลดเสร็จก่อนเปิดหน้าพิมพ์ ปิด JavaScript การเข้าถึงไฟล์และเครือข่ายในหน้าพิมพ์แยก ภาพหรือฟอนต์ภายนอกอาจไม่แสดง ต้องตรวจบิลจริง
- ไม่ใช้ APK updater และช่องดาวน์โหลด Takeaway เดิม ยังไม่เปิดการแจกอัตโนมัติหรือ Play Store

## ขอบเขตความปลอดภัย

Backend ตรวจ company, brand, branch, product, device และสิทธิ์ที่ยังมีอยู่ในฐานข้อมูลทุกคำขอของ native POS มี allowlist แยก endpoint และ HTTP method ปฏิเสธ ERP admin การข้ามผลิตภัณฑ์ การเปลี่ยน header/query ให้เป็นสาขาอื่น และ catalog scope ที่ไม่ตรงผลิตภัณฑ์ Refresh คง session แบบจำกัดขอบเขต ไม่เปลี่ยนเป็น token หลังบ้าน

Restaurant และ Retail ต้องใช้พนักงานที่ได้รับสิทธิ์จริง ไม่ใช้ superuser หรือ wildcard ส่วนข้อยกเว้นบัญชีทดสอบ Takeaway ที่มีอยู่เดิมยังอยู่ในนโยบายเดิม การค้นหาสมาชิกในแอปรวมใช้ endpoint ใหม่ที่ตรวจบริษัทจาก session ไม่ใช้ public search ที่อาจอ้างอิงบริษัทเริ่มต้น

Native session ใช้ secure storage แยก namespace `foodchainservice.pos.uat` และฐานข้อมูล `FoodchainservicePOSUATDatabase` มีตัวระบุเจ้าของข้อมูลแยกจาก session เพื่อห้ามผู้ใช้หรือร้านใหม่เข้าทับข้อมูลค้าง แม้ session เดิมหายหรือถูกเพิกถอน ไม่อ่าน session หรือย้าย pending sales จากแอป Takeaway เดิม

ห้ามออกจากระบบหรือเปลี่ยนร้านขณะมีบิลกำลังทำ คำขอเขียนที่ยังไม่จบ หรือข้อมูลค้างส่ง ตรวจทั้งคิว Takeaway, POS, Restaurant และ local hold drafts ก่อนล้างข้อมูล การล้างทำเฉพาะหลังตรวจว่าปลอดภัย ไม่ถือว่ามีอินเทอร์เน็ตเท่ากับส่งข้อมูลสำเร็จ

Android ปิด backup และ device transfer ของข้อมูลแอป ไม่อนุญาต cleartext หรือ remote WebView navigation และไม่มีสิทธิ์ติดตั้ง APK จากแอปนี้ Production release tasks ยังถูกบล็อก

## วิธีสร้างและทดสอบ

ทำงานใน `frontend` โดยใช้ Java 21 และ Android SDK ที่ติดตั้งไว้:

```sh
npm ci
npm run dev:pos
npm run type-check
npm run e2e:pos-native
npm run pos:android:apk
```

ตรวจ native lint ใน `frontend/android-pos` ด้วย `./gradlew lintDebug` และตรวจข้อจำกัดของ native source จากรากโปรเจกต์ด้วย `node scripts/check-mobile-pos-native.mjs`

Build อ่านเฉพาะ UAT origins ที่กำหนด ไม่รับ tenant หรือ auto-login จาก .env ทั่วไป Onboarding ใช้ `https://uat-pos.foodchainservice.com/api/v1` แล้วใช้ host ของ Takeaway, Restaurant หรือ Retail ตาม signed session ลูกค้าสแกน QR ใช้ HTTPS origin ของ Restaurant ไม่ใช่ localhost ของแอป

Backend ใหม่อยู่ที่ `mobile_pos_auth.py` และ `mobile_pos_policy.py` เชื่อมใน `auth_service.py`, `dependencies.py` และ `main.py` ไม่มี database migration ในชุดนี้

## ผลตรวจในเครื่อง

- Backend mobile POS และ Takeaway boundary ผ่าน 15 tests และ platform auth security ผ่าน 10 tests เป็น automated tests ไม่ใช่ธุรกรรมกับ UAT จริง
- Browser POS ผ่าน 9 กรณีไม่ซ้ำ: launcher, สิทธิ์และห้ามข้ามผลิตภัณฑ์, restore/logout, สถานะ offline, Restaurant, Retail scan, token ผิดผลิตภัณฑ์, คำขอเขียนค้าง และข้อมูลค้างเมื่อ session หาย ใช้ API จำลอง
- Regression Takeaway เดิมผ่าน 4 กรณีที่กระทบ: ห้ามเปิด URL เกินสิทธิ์ logout/เปลี่ยนบริษัท ข้อมูลออฟไลน์ และ business code ไม่ตรง ใช้ค่าช่องอัปเดตทดสอบ ไม่แก้ production signing
- TypeScript, POS production-mode bundle และ native source checks ผ่าน Bundle ไม่มี auto-login หรือ legacy updater แต่ยังมี API helpers ที่ใช้ร่วม Backend เป็นผู้บังคับขอบเขตสิทธิ์
- Android assembleDebug และ lintDebug ผ่าน ไม่มี lint errors มี 15 warnings ไม่ปิด lint gate เพื่อข้ามข้อผิดพลาด
- APK รุ่น `0.1.0-uat.2` code 2 อยู่ที่ `frontend/android-pos/app/build/outputs/apk/debug/app-debug.apk` เป็น debug candidate ขนาดประมาณ 5.7 MB ยังใช้ไอคอน template
- SHA256: `3709c8eba2758420c72aed23266dd2edc369cf8d7fcf41fbde29e1ff8cac0461`
- ไม่พบอุปกรณ์ Android หรือ emulator เชื่อมต่อ จึงยังไม่ได้ติดตั้ง APK หรือรัน instrumentation บนอุปกรณ์จริง
- ไม่มีการ commit, push หรือ deploy ในรอบนี้ งานอยู่บน branch `codex/pos-ios-android-foundation` ใน worktree `/Users/user/.codex/worktrees/pos-ios-android/restaurant`

## ขั้นตอนก่อนแจกใช้งาน

1. ตรวจและ commit งานใน repository `chaiyanutaiagent/restaurant` เท่านั้น ก่อน push ตรวจ origin, gh repo view, git status และ branch ตาม AGENTS.md
2. สำรอง release UAT ปัจจุบันและ deploy backend ชุดนี้โดยไม่เปลี่ยน Production flags ตรวจ CORS `https://localhost` บนทุก host ที่แอปใช้ แล้วทดสอบ login/refresh/revoke ด้วยพนักงานจริงของแต่ละผลิตภัณฑ์
3. ตรวจ smoke กับ UAT: ขายเงินสด พักและเรียกบิล คืนสินค้า เปิดโต๊ะ QR สั่งอาหาร ส่งครัว และปิดกะ ตรวจรายการซ้ำและสต๊อกตามผลิตภัณฑ์ ห้ามถือว่าผล mock browser tests ยืนยันขั้นนี้
4. ติดตั้ง APK บน Android เป้าหมาย ตรวจกล้อง การปฏิเสธสิทธิ์ Bluetooth บิลภาษาไทย QR ลิ้นชักเงิน PromptPay เน็ตหลุด การพัก/เปิดแอปใหม่และอัปเดตโดยไม่สูญเสียคิว ส่งงานพิมพ์สำเร็จไม่ยืนยันว่ากระดาษออกครบ
5. ก่อน Production ต้องกำหนด app ID, release signing key/เจ้าของกุญแจ ช่องแจกอัปเดต ไอคอนจริง ข้อมูลความเป็นส่วนตัว และผ่านเกณฑ์อนุมัติ ห้ามนำ debug APK ไปแทนระบบขายจริง

Rollback UAT ใช้ backend release เดิมและหยุดแจก APK ใหม่ ชุดนี้ไม่มี schema migration แต่การ rollback จะทำให้ native POS session ใหม่ใช้ API ไม่ได้ ห้ามถอนแอปหรือล้างข้อมูลค้างส่ง ให้คงข้อมูลไว้จนกู้การเชื่อมต่อหรือกระทบยอดสำเร็จ

## สถานะ iOS

มี scaffold ของ Capacitor 7.6.8 รหัส `com.foodchainservice.pos.uat` เวอร์ชัน 0.1.0 build 1 เท่านั้น เครื่องนี้ไม่มี Xcode เต็มและ CocoaPods จึงยังไม่ build/sign/TestFlight หรือทดสอบ Keychain และกล้อง การ copy assets และตรวจ syntax ครั้งก่อนเป็นผล Foundation ไม่ใช่ผลทดสอบ native integration รุ่นปัจจุบัน

ก่อนทดสอบ iOS ต้องติดตั้งเครื่องมือและใช้ `npm run pos:ios:sync` ไม่เรียก add ios ทับโปรเจกต์เดิม ผล preflight UAT ครั้งก่อนวันที่ 4 ตุลาคม 2026: Android origin ได้ 200 ส่วน `capacitor://localhost` ได้ 400 จึงต้องเพิ่ม origin iOS แบบระบุเจาะจงก่อน ไม่ใช้ wildcard

## เอกสารอ้างอิง

- [Capacitor 7 iOS](https://capacitorjs.com/docs/v7/ios) และ [การเตรียมเครื่องมือ](https://capacitorjs.com/docs/v7/getting-started/environment-setup)
- [Android HTML printing](https://developer.android.com/training/printing/html-docs) อธิบายการรอ WebView โหลดเสร็จและข้อจำกัดการพิมพ์ HTML
