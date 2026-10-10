import axios from "axios";

const labels: Record<string, string> = {
  code: "รหัสสาขา", name: "ชื่อสาขา", name_en: "ชื่อภาษาอังกฤษ", phone: "โทรศัพท์", email: "อีเมล",
  latitude: "ละติจูด", longitude: "ลองจิจูด", google_maps_url: "ลิงก์แผนที่", sort_order: "ลำดับแสดงผล",
  brand_slug: "รหัสแบรนด์", brand_name: "ชื่อแบรนด์", branch_code: "รหัสสาขา", branch_name: "ชื่อสาขา",
  module_key: "ประเภทกิจการ", branch_type: "ประเภทสาขา", storefront_mode: "รูปแบบร้าน", idempotency_key: "รหัสคำขอ",
};

export function companySetupErrorMessage(error: unknown): string {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : "บันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่";
  if (!error.response) return "เชื่อมต่อระบบไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่";
  const detail = error.response.data?.detail;
  if (Array.isArray(detail)) return detail.map((issue) => {
    const field = Array.isArray(issue?.loc) ? issue.loc.at(-1) : "";
    const label = labels[field] ?? "ข้อมูลที่กรอก";
    let message = "รูปแบบไม่ถูกต้อง กรุณาตรวจสอบข้อมูล";
    if (issue?.type === "string_too_long" && typeof issue.ctx?.max_length === "number") message = `กรอกได้ไม่เกิน ${issue.ctx.max_length} ตัวอักษร`;
    else if (issue?.type === "missing" || issue?.type === "string_too_short") message = "กรุณากรอกข้อมูลให้ครบ";
    else if (field === "brand_slug") message = "ใช้ตัวอักษร a–z ตัวเลข และขีดกลาง ไม่ใช่ชื่อเว็บไซต์";
    else if (field === "branch_code") message = "ใช้ตัวอักษรอังกฤษ ตัวเลข ขีดกลาง หรือขีดล่าง เช่น BKK-01";
    else if (field === "latitude") message = "กรอกตัวเลขตั้งแต่ -90 ถึง 90";
    else if (field === "longitude") message = "กรอกตัวเลขตั้งแต่ -180 ถึง 180";
    return `${label}: ${message}`;
  }).join("\n");
  if (detail && typeof detail.message === "string") return detail.message;
  if (typeof detail === "string") {
    if (detail.startsWith("Plan limit reached")) return "จำนวนแบรนด์หรือสาขาถึงขีดจำกัดของแพ็กเกจแล้ว กรุณาติดต่อผู้ดูแล";
    if (detail === "Branch code already exists") return "รหัสสาขานี้ถูกใช้แล้ว กรุณาใช้รหัสอื่น";
    if (/[\u0E00-\u0E7F]/.test(detail)) return detail;
  }
  if (error.response.status === 409) return "ข้อมูลซ้ำหรือไม่ตรงกับแบรนด์/สาขาที่มีอยู่ กรุณาตรวจสอบรหัสและประเภทกิจการ";
  if (error.response.status === 403) return "บัญชีนี้ไม่มีสิทธิ์ดำเนินการ หรือแพ็กเกจยังไม่เปิดประเภทกิจการนี้ กรุณาติดต่อเจ้าของบริษัท";
  if (error.response.status === 422) return "ข้อมูลไม่ผ่านการตรวจสอบ กรุณาตรวจสอบช่องที่กรอก";
  return "ระบบบันทึกข้อมูลไม่สำเร็จ กรุณาลองใหม่ หากยังพบปัญหาให้ติดต่อผู้ดูแล";
}
