// Never render validation `input` or `ctx`: they can contain credentials.
const labels: Record<string, string> = {
  name: "ชื่อบริษัท", business_slug: "Business URL", name_en: "ชื่ออังกฤษ",
  tax_id: "เลขประจำตัวผู้เสียภาษี", email: "อีเมลบริษัท", phone: "เบอร์โทรศัพท์",
  currency: "สกุลเงิน", timezone: "เขตเวลา", plan_code: "Plan code",
  reason: "เหตุผลที่เปิด Company", "owner.username": "Username Owner",
  "owner.password": "รหัสผ่าน Owner", "owner.email": "อีเมล Owner",
  "owner.display_name": "ชื่อ Company Owner", plan_limits: "จำนวนสิทธิ์ใช้งาน",
  "plan_limits.brands": "จำนวนแบรนด์", "plan_limits.branches": "จำนวนสาขา",
  "plan_limits.users": "จำนวนผู้ใช้งาน", "plan_limits.devices": "จำนวนอุปกรณ์",
};

export function platformValidationMessages(detail: unknown): string[] {
  if (!Array.isArray(detail)) return [];
  return detail.flatMap((entry: unknown) => {
    if (!entry || typeof entry !== "object") return [];
    const issue = entry as { loc?: unknown; type?: unknown; msg?: unknown; ctx?: { min_length?: unknown; max_length?: unknown } };
    const path = Array.isArray(issue.loc)
      ? issue.loc.filter((part) => typeof part === "string" || typeof part === "number").filter((part) => part !== "body").join(".")
      : "";
    const label = labels[path] ?? (path || "ข้อมูลที่ส่ง");
    let message = "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบรูปแบบและค่าที่กรอก";
    if (issue.type === "missing") message = "กรุณากรอกข้อมูล";
    else if (issue.type === "string_too_short" && typeof issue.ctx?.min_length === "number") message = `ต้องมีอย่างน้อย ${issue.ctx.min_length} ตัวอักษร`;
    else if (issue.type === "string_too_long" && typeof issue.ctx?.max_length === "number") message = `ต้องมีไม่เกิน ${issue.ctx.max_length} ตัวอักษร`;
    else if (path === "owner.username") message = "ใช้ตัวอักษรอังกฤษ ตัวเลข จุด ขีดกลาง หรือขีดล่าง 3–100 ตัว เริ่มด้วยตัวอักษรหรือตัวเลข ห้ามใช้ช่องว่างหรือ @";
    else if (path === "business_slug") message = "ใช้ a–z ตัวเลข หรือขีดกลาง 3–63 ตัว ห้ามขึ้นต้นหรือลงท้ายด้วยขีดกลาง ห้ามขีดกลางติดกัน และห้ามใช้คำสงวน เช่น restaurant, admin, pos";
    else if (path === "plan_code") message = "ใช้ตัวอักษรอังกฤษ ตัวเลข ขีดกลาง หรือขีดล่าง 2–50 ตัว เริ่มด้วยตัวอักษรหรือตัวเลข";
    else if (path.startsWith("plan_limits")) message = "กรอกจำนวนเต็มตั้งแต่ 0 ถึง 1,000,000 (0 หมายถึงไม่จำกัด)";
    else if (typeof issue.msg === "string" && issue.msg.endsWith("is required")) message = "กรุณากรอกข้อมูล ห้ามเว้นว่างหรือมีแต่ช่องว่าง";
    return [`${label}: ${message}`];
  });
}
