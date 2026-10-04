# WP20 — Takeaway Android / Device Parity

วันที่: 2026-09-17

สถานะ: **implementation completed — รอ native build และ physical-device evidence ใน WP24**

## ผลลัพธ์

- แยก Android identity เป็น `com.foodchainservice.takeaway` และชื่อแอป `Foodchainservice Takeaway`
- แยก UAT package ด้วย suffix `.uat` เพื่อให้ติดตั้งคู่กับ Production ได้
- เพิ่ม Capacitor native plugin สำหรับอ่านเครื่องพิมพ์ Bluetooth ที่จับคู่และส่งข้อมูล ESC/POS
- เพิ่ม permission flow สำหรับ Android 12+ และ fallback ไป browser print เมื่อไม่ได้อยู่ใน Android app
- เพิ่มหน้า `/takeaway/store/device` สำหรับเลือกเครื่องพิมพ์ ทดสอบพิมพ์ และดู signed app update
- Counter เลือกใช้ native printer เมื่อกำหนดไว้ และยังบันทึก reprint audit ตามเดิม
- Release build ปฏิเสธการสร้าง unsigned artifact เมื่อไม่มี signing environment ครบ
- App update ใช้ Ed25519 signed manifest, ตรวจ package identity และ SHA-256 ก่อนแสดงลิงก์ APK
- เพิ่ม script สร้าง/ตรวจ release manifest และ JSON schema กลาง

## หลักฐานที่ผ่านแล้ว

- Frontend type-check: ผ่าน
- Android web build + Capacitor sync: ผ่าน (4,223 modules, 3 Capacitor plugins)
- Signed manifest synthetic Ed25519 roundtrip: ผ่าน
- Android boundary structural check: ผ่าน
- Package เดิม `com.chaiyanutaiagent.restaurant` ไม่เหลือใน Android source

## Gate ที่ยังเปิดค้างอย่างตั้งใจ

- เครื่อง Mac ปัจจุบันยังไม่มี Java runtime และ Android SDK จึงยังไม่มี native Gradle compile/signed APK evidence
- ยังไม่ได้ทดสอบบนเครื่อง Android จริงกับ Bluetooth printer, permission deny/retry, paper-out และ reconnect
- Public key, manifest URL, production keystore และ APK จริงต้องตั้งผ่าน secret/release environment เท่านั้น

รายการข้างต้นเป็นส่วนของ WP24 และ WP26; เอกสารนี้ไม่ถือว่า physical UAT หรือ production activation ผ่านแล้ว
