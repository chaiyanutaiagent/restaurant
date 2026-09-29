export const platformPasswordRules = [
  { label: "อย่างน้อย 8 ตัวอักษร", valid: (value: string) => value.length >= 8 },
  { label: "มีตัวพิมพ์ใหญ่", valid: (value: string) => /[A-Z]/.test(value) },
  { label: "มีตัวพิมพ์เล็ก", valid: (value: string) => /[a-z]/.test(value) },
  { label: "มีตัวเลข", valid: (value: string) => /[0-9]/.test(value) },
  { label: "มีอักขระพิเศษ", valid: (value: string) => /[^A-Za-z0-9\s]/.test(value) },
  { label: "ไม่มีช่องว่าง", valid: (value: string) => !/\s/.test(value) },
] as const;

export function isPlatformPasswordValid(value: string): boolean {
  return platformPasswordRules.every((rule) => rule.valid(value));
}
