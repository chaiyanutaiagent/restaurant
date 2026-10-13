import { useRef, useState } from "react";
import axios from "axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { categoryApi } from "@/lib/productApi";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";
import type { Category } from "@/types/product";

export const categoryNameKey = (name: string) => name.trim().replace(/\s+/g, " ").toLocaleLowerCase("th-TH");
const contextKey = () => {
  const s = useAuthStore.getState();
  return `${s.companyId}:${s.brandId}:${s.branchId}:${s.businessType}:${s.targetDatabase}`;
};

type Props = { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (category: Category) => void | Promise<void> };

export default function RetailCategoryCreateDialog(props: Props): JSX.Element {
  const identity = useAuthStore(s => `${s.companyId}:${s.brandId}:${s.branchId}:${s.businessType}:${s.targetDatabase}`);
  return <CategoryForm key={`${identity}:${props.open}`} {...props} identity={identity} />;
}

function CategoryForm({open,onOpenChange,onCreated,identity}: Props & {identity: string}): JSX.Element {
  const online = useOnlineStatus();
  const [name,setName] = useState("");
  const [busy,setBusy] = useState(false);
  const [uncertain,setUncertain] = useState(false);
  const [error,setError] = useState("");
  const [existing,setExisting] = useState<Category|null>(null);
  const request = useRef<{name:string;code:string}|null>(null);
  const inFlight = useRef(false);
  async function finish(category: Category) {
    if (identity !== contextKey()) return;
    await onCreated(category);
    onOpenChange(false);
  }
  async function selectExisting(category: Category) {
    if (inFlight.current || !online) return;
    inFlight.current=true;setBusy(true);
    try {await finish(category);}
    catch {setError("เลือกหมวดไม่สำเร็จ กรุณาลองอีกครั้ง");}
    finally {inFlight.current=false;setBusy(false);}
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (inFlight.current || !online) return;
    const state = useAuthStore.getState();
    if (identity !== contextKey() || state.businessType !== "retail_pos" || state.targetDatabase !== "retail_pos" || !state.hasPermission("inventory.product.create")) {
      setError("กรุณาเลือกบริบท Retail และตรวจสิทธิ์เพิ่มสินค้า");return;
    }
    const cleanName = name.trim().replace(/\s+/g," ");
    if (!cleanName) {setError("กรุณาระบุชื่อหมวดสินค้า");return;}
    inFlight.current=true;setBusy(true);setError("");setExisting(null);
    let submitted=false;
    try {
      const rows = (await categoryApi.list()).data.data as Category[];
      if (identity !== contextKey()) return;
      // Resolve an uncertain response by the same unique code before another POST.
      const saved = request.current && rows.find(row=>row.code===request.current?.code);
      if (saved) {await finish(saved);return;}
      const duplicate = rows.find(row=>categoryNameKey(row.name)===categoryNameKey(cleanName));
      if (duplicate) {
        if (duplicate.is_active) {setExisting(duplicate);setError("มีหมวดชื่อนี้แล้ว สามารถเลือกหมวดเดิมได้");}
        else setError("มีหมวดชื่อนี้ที่ปิดใช้งานอยู่ กรุณาให้ผู้ดูแลตรวจสอบ");
        return;
      }
      request.current ??= {name:cleanName,code:`POS-${crypto.randomUUID()}`};
      submitted=true;
      const category = (await categoryApi.create({...request.current,is_active:true})).data.data as Category;
      await finish(category);
    } catch(e) {
      const status = axios.isAxiosError(e) ? e.response?.status : undefined;
      if (submitted && (!status || status>=500 || status===409)) {
        setUncertain(true);
        setError("ยังยืนยันผลบันทึกไม่ได้ กดตรวจผลอีกครั้ง ระบบจะค้นหาคำขอเดิมก่อนสร้างหมวด");
      } else {
        const detail = axios.isAxiosError(e) ? e.response?.data?.detail : null;
        setError(typeof detail==="string" ? detail : "โหลดหรือบันทึกหมวดไม่สำเร็จ กรุณาลองอีกครั้ง");
        if (!uncertain) request.current=null;
      }
    } finally {inFlight.current=false;setBusy(false);}
  }
  return <Dialog open={open} onOpenChange={next=>{if(!busy)onOpenChange(next);}}>
    <DialogContent className="max-w-md" onInteractOutside={e=>{if(busy)e.preventDefault();}}>
      <DialogHeader><DialogTitle>เพิ่มหมวดสินค้า</DialogTitle><DialogDescription>หมวดใช้ร่วมกันใน Retail ของบริษัทที่เลือก ไม่สร้างสินค้าและไม่เพิ่มสต๊อก</DialogDescription></DialogHeader>
      <form onSubmit={save} className="space-y-4">
        <label className="block font-medium" htmlFor="retail-category-name">ชื่อหมวดสินค้า</label>
        <Input id="retail-category-name" className="h-12 text-base" maxLength={255} required value={name} disabled={busy||uncertain} onChange={e=>{setName(e.target.value);setExisting(null);setError("");}} placeholder="เช่น เครื่องดื่ม ของใช้ในบ้าน" />
        {!online&&<p role="alert" className="text-sm text-amber-700">ต้องออนไลน์เพื่อเพิ่มหมวดสินค้า</p>}
        {error&&<p role="alert" className="text-sm text-red-700">{error}</p>}
        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={()=>onOpenChange(false)}>ยกเลิก</Button>
          {existing ? <Button type="button" disabled={busy||!online} onClick={()=>void selectExisting(existing)}>ใช้หมวดเดิม</Button> : <Button type="submit" disabled={busy||!online}>{busy?"กำลังตรวจสอบ...":uncertain?"ตรวจผลอีกครั้ง":"บันทึกหมวด"}</Button>}
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}
