// A card is not an entitlement: login resolves only server-authorized branches.
export const POS_PRODUCTS = [
  { id: "takeaway", name: "Takeaway", description: "รับสินค้าส่วนกลาง ขาย เตรียมสินค้า และจัดการกะ",
    path: "/connect/takeaway", available: true },
  { id: "restaurant", name: "Restaurant", description: "เปิดโต๊ะ รับออร์เดอร์ ส่งครัว และชำระเงิน",
    path: "/connect/restaurant", available: true },
  { id: "retail", name: "Retail", description: "สแกนสินค้า ขายปลีก คืนสินค้า และปิดกะ",
    path: "/connect/retail_pos", available: true },
] as const;
