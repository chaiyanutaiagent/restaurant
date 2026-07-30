# วิธีเปิดใช้งาน Restaurant POS

## ความต้องการ
- Docker Desktop (ต้องเปิดไว้ก่อน)
- macOS

## วิธีเปิดระบบ
### วิธีที่ 1: ดับเบิ้ลคลิก
ดับเบิ้ลคลิกที่ไฟล์ `start.command` ใน Finder

### วิธีที่ 2: Terminal
```bash
cd '/Users/user/Projects/restaurant'
./start.sh
```

## เข้าใช้งาน
- เปิด Browser: http://localhost:8081
- Username: `admin`
- Password: ใช้ค่าจาก `DEFAULT_ADMIN_PASSWORD` ในไฟล์ `.env` ของเครื่อง
- Company ID: ใช้ ID ของบริษัทที่ระบบใหม่สร้างขึ้น หรือตั้ง `VITE_COMPANY_ID`

## ปิดระบบ
### วิธีที่ 1: ดับเบิ้ลคลิก
ดับเบิ้ลคลิกที่ไฟล์ `stop.command` ใน Finder

### วิธีที่ 2: Terminal
```bash
./stop.sh
```
หรือเปิด Docker Desktop แล้วกด Stop All

## หมายเหตุ
- ครั้งแรกใช้เวลา build ~5-10 นาที
- ครั้งต่อไปเร็วขึ้น ~1-2 นาที
- ข้อมูลถูกเก็บใน Docker volume (ไม่หายเมื่อ stop)
