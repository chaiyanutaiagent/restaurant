# Foodchainservice POS Android UAT 3 deployment

วันที่ 5 ตุลาคม 2026 ตามเวลาไทย นำ backend สำหรับแอป POS รวมขึ้น UAT แล้ว และเผยแพร่ APK รุ่นทดลองแยกจาก Takeaway เดิม ยังไม่อนุมัติ Production และยังไม่ผ่านการตรวจฮาร์ดแวร์จริง

## รุ่นและขอบเขต

- Repository: `chaiyanutaiagent/restaurant` สาขา `codex/pos-ios-android-foundation`
- Backend source: `ca0e3fe` รวมงานล่าสุดจาก `origin/main` ก่อน deploy เพื่อคง security fixes และ UAT superadmin projection ของรุ่น `3760d60`
- Backend image: `restaurant-pos-backend:uat-mobile-pos-ca0e3fe`
- Image ID: `sha256:18d478d9996ceda887f4c17e4f1e60657bc31ccbb8acba856bc1c39dc486a30d`
- Release directory: `/home/behappyaiagent/restaurant-uat-releases/ca0e3fe`
- APK source: `1ebdc62` รวม Axios 1.20.0 จากงานล่าสุด Package `com.foodchainservice.pos.uat`, version `0.1.0-uat.3`, code 3
- เปลี่ยนเฉพาะ container backend ของ `restaurant-pos-uat-drill` ไม่เปลี่ยน frontend, PostgreSQL, Redis, nginx หรือ cloudflared และไม่เปลี่ยน container ของ Production
- เปรียบเทียบ environment ทั้งชุดก่อนและหลังแล้วตรงกัน ไม่มีการเปลี่ยน flags, data source, hostname หรือ schema migration

## APK สำหรับทดสอบ

[ดาวน์โหลด Foodchainservice POS UAT 3](https://uat-pos.foodchainservice.com/downloads/foodchainservice-pos/foodchainservice-pos-0.1.0-uat.3.apk)

SHA256: `c344a1f00d259fd8058534ca032e1df63128527e77491038f2cacd4bc9a1041f`

เป็น debug-signed UAT candidate ไม่ใช่ Play Store release ตรวจ package/version และลายเซ็นไฟล์ผ่าน แยกจาก package และช่องอัปเดต Takeaway เดิม ไม่มีการแก้ `takeaway-store/latest.json` ซึ่งยังมี SHA256 `a544e0d4ab201a1fe61acbb4ed9ca53c789f6643673fe305ed4b261f3127d85c`

เลือกผลิตภัณฑ์แล้วใช้ Business Code `sketch-biz` และบัญชีพนักงานที่ได้รับสิทธิ์ Restaurant/Retail ไม่รองรับ superuser หรือ wildcard อย่าถอนแอปเก่าหรือล้างข้อมูลที่ยังค้างส่ง

## ผลตรวจ

- Image ใหม่ผ่าน backend mobile boundary 15 tests และ platform auth security 10 tests ก่อนสลับบริการ
- APK ใหม่ผ่าน TypeScript, bundle boundary, Android build และ lint ไม่มี lint errors มี 15 warnings
- Browser POS หลังรวม dependency ใหม่ผ่าน 9 tests ใช้ API จำลอง และ `npm audit --omit=dev` ไม่พบช่องโหว่ ส่วน build/test dependencies ยังมี 10 findings ตามงาน readiness เดิม ไม่ได้บังคับอัปเกรดแบบ breaking change
- Public health และ Android CORS preflight ผ่าน `uat-pos`, `uat-takeaway`, `uat-restaurant`, `uat-retail` สำหรับ origin `https://localhost`
- Backend หลัง deploy healthy, restart count 0 ไม่พบ critical error/5xx ในช่วงตรวจ
- ตรวจบัญชีพนักงานผ่าน API จริงภายใน UAT โดยใช้ Host ของผลิตภัณฑ์เพื่อให้ credentials อยู่บนเซิร์ฟเวอร์ ไม่ใช่ผลทดสอบบน Android ผ่านอินเทอร์เน็ต

| บัญชี | ระบบและสาขา | จำนวนแถวสินค้าในผลอ่าน |
| --- | --- | --- |
| `test.chambo.store-cashier` | Takeaway BKK-01 | 46 |
| `test.kpp.cashier` | Restaurant KPP-01 | 20 |
| `test.tlk.cashier` | Restaurant TLK-01 | 4 |
| `test.tlm.cashier` | Retail TLM-01 | 17 |

ทั้งสี่บัญชีผ่าน login, อ่านข้อมูลตามสิทธิ์, refresh ที่คงบริบทเดิม, การปฏิเสธข้ามสาขา/หลังบ้าน และ logout ที่ทำให้ token ใช้งานต่อไม่ได้ การอ่านโต๊ะคาดหวัง 403 เมื่อ cashier ไม่มี `fb.menu.view` ไม่เพิ่มสิทธิ์เพื่อให้ test ผ่าน จำนวนแถวสินค้าข้างต้นไม่ใช่จำนวนสินค้าที่มีสต๊อกพร้อมขาย

ใช้รหัสที่ตั้งไว้บน UAT ปัจจุบัน ไม่รีเซ็ตรหัสพนักงาน รหัสเก่าจากประวัติการสนทนาไม่ตรงข้อมูลปัจจุบัน มีการสร้าง/เพิกถอน session ทดสอบและอัปเดตเวลาเข้าใช้ตามปกติ แต่ไม่สร้างรายการขาย ชำระเงิน สต๊อก หรือกะ

## Backup และ rollback

Backup อยู่ที่ `/home/behappyaiagent/restaurant-uat-deploy-backups/mobile-pos-before-ca0e3fe` สิทธิ์ไดเรกทอรี 700 เก็บ environment/config เดิม container snapshot และ backend image เดิม พร้อม custom-format dumps ของ Platform, Legacy, Restaurant, Retail และ Takeaway รวมถึง uploads ทั้ง 5 dumps ผ่าน `pg_restore --list` และไฟล์ dump/archive ผ่าน checksum

ไม่มี schema migration จึงใช้ app-only rollback โดยไม่ทับธุรกรรมใหม่:

```sh
cd /home/behappyaiagent/restaurant-uat-releases/3760d60
BACKEND_IMAGE=restaurant-pos-backend:uat-readiness-3760d60 docker compose \
  -p restaurant-pos-uat-drill --env-file .env.uat \
  -f docker-compose.prod.yml -f docker-compose.uat.yml \
  -f docker-compose.uat-superadmin.yml \
  up -d --no-deps --no-build backend
```

ต้องกำหนด image เดิมชัดเจน เพราะค่า image ใน `.env.uat` ไม่ใช่ตัวระบุรุ่นที่เคยรันจริง หาก image ถูกล้างภายหลัง ให้โหลด `backend-image.tar.gz` ที่สำรองไว้ก่อน ไม่ใช้คำสั่ง down หรือ restore database เพื่อย้อนเพียงแอป ตรวจ health หลัง rollback และเก็บข้อมูลค้างของ APK ใหม่ไว้จนกู้การเชื่อมต่อได้

## สิ่งที่ยังรอตรวจรับ

ติดตั้ง APK บน Android จริง ตรวจ login ผ่านเครือข่ายจริง กล้อง การพิมพ์ Bluetooth/ภาษาไทย/QR ลิ้นชักเงิน เงินสด PromptPay การทำรายการซ้ำเมื่อเน็ตหลุด การพักแอป และอัปเดตโดยรักษาข้อมูลค้าง ก่อนอนุมัติใช้งานจริง ยังไม่ได้ merge สาขานี้เข้า main หรือเปิด Production release flags
