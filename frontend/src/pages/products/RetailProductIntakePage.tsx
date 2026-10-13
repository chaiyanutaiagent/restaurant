import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Link } from "react-router-dom";
import { Camera, ScanBarcode } from "lucide-react";
import api from "@/lib/api";
import { categoryApi, unitApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ProductBarcodeScanner from "@/components/products/ProductBarcodeScanner";
import type { Category, Unit } from "@/types/product";
import type { ApiResponse } from "@/types/api";

type Existing = {id:string;name:string;barcode:string;sku:string;selling_price:string;cost_price:string};
type Receipt = {product_id:string;name:string;created:boolean;qty_received:string;replayed:boolean};
const empty = {name:"",description:"",unit_id:"",category_id:"",selling_price:"0",cost_price:"0",qty:"0",location_id:"",vat_type:"included",vat_rate:"7"};

function Workspace(): JSX.Element {
  const online = useOnlineStatus();
  const branchId = useAuthStore(s=>s.branchId);
  const companyId = useAuthStore(s=>s.companyId);
  const brandId = useAuthStore(s=>s.brandId);
  const hasPermission = useAuthStore(s=>s.hasPermission);
  const canReceive = ["inventory.stock.adjust","brand.store.stock.adjust","brand.central.raw_stock.manage","brand.central.ready_stock.manage"].some(hasPermission);
  const cache = useQueryClient();
  const [barcode,setBarcode] = useState("");
  const [checked,setChecked] = useState("");
  const [existing,setExisting] = useState<Existing|null>(null);
  const [fields,setFields] = useState(empty);
  const [image,setImage] = useState<File|null>(null);
  const [preview,setPreview] = useState("");
  const [scanning,setScanning] = useState(false);
  const [busy,setBusy] = useState(false);
  const [locked,setLocked] = useState(false);
  const [error,setError] = useState("");
  const [receipt,setReceipt] = useState<Receipt|null>(null);
  const pending = useRef<FormData|null>(null);
  const inFlight = useRef(false);
  const lookupSequence = useRef(0);
  const units = useQuery({queryKey:["retail-intake",companyId,brandId,branchId,"units"],queryFn:async()=>(await unitApi.list()).data as ApiResponse<Unit[]>});
  const categories = useQuery({queryKey:["retail-intake",companyId,brandId,branchId,"categories"],queryFn:async()=>(await categoryApi.list()).data as ApiResponse<Category[]>});
  const locations = useQuery({queryKey:["retail-intake",companyId,brandId,branchId,"locations"],enabled:canReceive,queryFn:async()=>(await stockApi.listLocations(branchId ?? undefined)).data.data});
  useEffect(()=>{if (!image) {setPreview("");return;} const url=URL.createObjectURL(image);setPreview(url);return()=>URL.revokeObjectURL(url);},[image]);
  function changeCode(value:string) {lookupSequence.current++;setBarcode(value);setChecked("");setExisting(null);setError("");}
  async function lookup(code=barcode) {
    if (!online || inFlight.current) return;
    const normalized=code.trim();
    if (!normalized || normalized.length>100) {setError("กรุณาระบุบาร์โค้ดไม่เกิน 100 ตัว");return;}
    const sequence=++lookupSequence.current;
    setBarcode(normalized);setBusy(true);setError("");setChecked("");
    try {
      const result=(await api.get<ApiResponse<{product:Existing|null}>>("/products/retail/intake-lookup",{params:{barcode:normalized}})).data.data.product;
      if(sequence!==lookupSequence.current)return;
      setExisting(result);setChecked(normalized);setImage(null);
      setFields(result?{...empty,name:result.name,selling_price:result.selling_price,cost_price:result.cost_price,qty:"1"}:empty);
    } catch(e) {if(sequence===lookupSequence.current)setError(message(e));} finally {setBusy(false);}
  }
  function message(e:unknown) {const detail=axios.isAxiosError(e)?e.response?.data?.detail:null;return typeof detail==="string"?detail:"ติดต่อระบบไม่ได้ กรุณาตรวจการเชื่อมต่อแล้วลองอีกครั้ง";}
  function selectImage(file?:File) {
    if(!file)return;
    if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>5*1024*1024){setError("ใช้รูป JPG, PNG หรือ WebP ขนาดไม่เกิน 5 MB");return;}
    setImage(file);setError("");
  }
  async function save(event:React.FormEvent) {
    event.preventDefault();
    if(inFlight.current||!online||checked!==barcode.trim())return;
    inFlight.current=true;setBusy(true);setError("");
    if(!pending.current){
      const form=new FormData();
      form.append("payload",JSON.stringify({...fields,request_id:crypto.randomUUID(),barcode:checked,
        unit_id:fields.unit_id||null,category_id:fields.category_id||null,location_id:fields.location_id||null,
        existing_product_id:existing?.id??null}));
      if(image&&!existing)form.append("image",image);
      pending.current=form;
    }
    setLocked(true);
    try {
      const result=(await api.post<ApiResponse<Receipt>>("/products/retail/intake",pending.current)).data.data;
      setReceipt(result);pending.current=null;setLocked(false);
      void cache.invalidateQueries();
    } catch(e) {
      const status=axios.isAxiosError(e)?e.response?.status:undefined;
      if(status&&status>=400&&status<500){pending.current=null;setLocked(false);setError(message(e));}
      else setError("ยังยืนยันผลบันทึกไม่ได้ กด ‘ลองบันทึกเดิมอีกครั้ง’ ระบบจะตรวจคำขอเดิมและไม่รับสต๊อกซ้ำ ห้ามปิดหน้านี้ระหว่างตรวจผล");
    } finally {setBusy(false);inFlight.current=false;}
  }
  useEffect(()=>{
    if(!locked)return;
    const guard=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};
    window.addEventListener("beforeunload",guard);return()=>window.removeEventListener("beforeunload",guard);
  },[locked]);
  const field=(key:keyof typeof empty,value:string)=>setFields(previous=>({...previous,[key]:value}));
  return <main className="min-h-screen bg-slate-50 p-4 md:p-8"><div className="mx-auto max-w-5xl space-y-5">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-blue-700">Retail · บริษัท / แบรนด์ / สาขาที่เลือก</p><h1 className="text-2xl font-bold">สแกนเพิ่มสินค้า / รับสต๊อก</h1></div>{!locked&&<Button asChild variant="outline"><Link to="/retail/pos">กลับหน้าขาย</Link></Button>}</header>
    <p className="text-sm text-slate-600">1 สแกนและตรวจสินค้า → 2 รายละเอียดและราคา → 3 คลังและจำนวน → 4 รูปสินค้า → บันทึก</p>
    {!online&&<p role="alert" className="rounded-xl bg-amber-100 p-4">ต้องออนไลน์เพื่อป้องกันสินค้าซ้ำและยืนยันยอดสต๊อก</p>}
    {error&&<p role="alert" className="rounded-xl bg-red-50 p-4 text-red-700">{error}</p>}
    {receipt?<section className="rounded-2xl border bg-white p-6" role="status"><h2 className="text-xl font-bold">บันทึกเรียบร้อย</h2><p>{receipt.name} · รับเข้า {receipt.qty_received} หน่วย</p><p>{receipt.created?"สร้างสินค้าใหม่แล้ว":"รับสินค้าเดิมเพิ่ม โดยไม่เปลี่ยนราคาขายหรือรูปเดิม"}</p><Button className="mt-4" onClick={()=>{setReceipt(null);setChecked("");setBarcode("");setFields(empty);setExisting(null);setImage(null);}}>เพิ่มสินค้าถัดไป</Button></section>:<>
      <section className="rounded-2xl border bg-white p-5"><label className="mb-2 block font-semibold" htmlFor="intake-barcode">บาร์โค้ดสินค้า</label><div className="flex flex-wrap gap-3">
        <Input id="intake-barcode" className="h-12 min-w-40 flex-1" value={barcode} maxLength={100} disabled={busy||locked} onChange={e=>changeCode(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();void lookup();}}} placeholder="สแกน / ยิงบาร์โค้ด / กรอกรหัส" />
        <Button className="h-12" disabled={busy||locked||!online} onClick={()=>void lookup()}>ตรวจบาร์โค้ด</Button>
        <Button variant="outline" className="h-12" disabled={busy||locked||!online} onClick={()=>setScanning(true)}><ScanBarcode className="mr-2 h-4 w-4"/>เปิดกล้องสแกน</Button>
      </div></section>
      {checked&&<form onSubmit={save} className="space-y-4"><fieldset disabled={busy||locked} className="grid gap-4 md:grid-cols-2">
        <section className="space-y-3 rounded-2xl border bg-white p-5"><h2 className="font-bold">{existing?"พบสินค้าเดิม — รับเพิ่ม":"สินค้าใหม่ — รายละเอียดและราคา"}</h2>
          <label className="block">ชื่อสินค้า<Input required value={fields.name} disabled={!!existing} maxLength={500} onChange={e=>field("name",e.target.value)}/></label>
          {!existing&&<><label className="block">รายละเอียด<Input value={fields.description} maxLength={2000} onChange={e=>field("description",e.target.value)}/></label>
          <label className="block">หน่วยสินค้า<select aria-label="หน่วยสินค้า" className="mt-1 h-12 w-full rounded border bg-white px-3" required value={fields.unit_id} onChange={e=>field("unit_id",e.target.value)}><option value="">เลือกหน่วย</option>{units.data?.data.filter(u=>u.is_active).map(u=><option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
          <label className="block">หมวดหมู่<select aria-label="หมวดหมู่" className="mt-1 h-12 w-full rounded border bg-white px-3" value={fields.category_id} onChange={e=>field("category_id",e.target.value)}><option value="">ไม่ระบุ</option>{categories.data?.data.filter(c=>c.is_active).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label></>}
          <label className="block">ราคาขาย (บาท)<Input type="number" min="0" step="0.0001" required value={fields.selling_price} disabled={!!existing} onChange={e=>field("selling_price",e.target.value)}/></label>
          {!existing&&<><label className="block">รูปแบบ VAT<select className="mt-1 h-12 w-full rounded border bg-white px-3" value={fields.vat_type} onChange={e=>field("vat_type",e.target.value)}><option value="included">รวม VAT</option><option value="excluded">แยก VAT</option><option value="exempt">ยกเว้น VAT</option></select></label><label className="block">อัตรา VAT (%)<Input type="number" min="0" max="100" step="0.01" required value={fields.vat_rate} onChange={e=>field("vat_rate",e.target.value)}/></label></>}
        </section>
        <section className="space-y-3 rounded-2xl border bg-white p-5"><h2 className="font-bold">{existing?"รับสินค้าเพิ่ม":"สต๊อกเริ่มต้น"}</h2><p className="text-sm text-slate-500">ใช้สาขา Retail ที่เลือกอยู่ หากต้องการสาขาอื่นให้กลับไปเปลี่ยนบริบทก่อนเริ่ม</p>
          <label className="block">ต้นทุนต่อหน่วย (บาท)<Input type="number" min="0" step="0.0001" required value={fields.cost_price} onChange={e=>field("cost_price",e.target.value)}/></label>
          <label className="block">จำนวนรับเข้า<Input type="number" min={existing?"0.0001":"0"} step="0.0001" required disabled={!canReceive} value={fields.qty} onChange={e=>field("qty",e.target.value)}/></label>
          {!canReceive&&<p className="text-sm text-amber-700">ไม่มีสิทธิ์รับเข้าคลัง สร้างสินค้าได้เฉพาะยอดเริ่มต้น 0</p>}
          {canReceive&&<label className="block">คลังรับสินค้า<select aria-label="คลังรับสินค้า" className="mt-1 h-12 w-full rounded border bg-white px-3" required={Number(fields.qty)>0} value={fields.location_id} onChange={e=>field("location_id",e.target.value)}><option value="">เลือกคลังในสาขานี้</option>{locations.data?.filter(l=>l.is_active&&l.branch_id===branchId).map(l=><option key={l.id} value={l.id}>{l.name} ({l.code})</option>)}</select></label>}
          {(units.isError||categories.isError||locations.isError)&&<p role="alert" className="text-red-600">โหลดหน่วย หมวดหมู่ หรือคลังไม่สำเร็จ กรุณาตรวจสิทธิ์และโหลดหน้าใหม่</p>}
          {!existing&&<div className="space-y-3 border-t pt-4"><h2 className="font-bold">รูปสินค้า (ไม่บังคับ)</h2><label className="block">แนบรูป<input className="block w-full py-2" type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>selectImage(e.target.files?.[0])}/></label><label className="block"><Camera className="mr-2 inline h-4 w-4"/>ถ่ายรูป<input className="block w-full py-2" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" onChange={e=>selectImage(e.target.files?.[0])}/></label>{preview&&<><img src={preview} alt="รูปสินค้าก่อนบันทึก" className="h-40 w-40 rounded-xl object-contain"/><Button type="button" variant="outline" onClick={()=>setImage(null)}>นำรูปออก</Button></>}</div>}
        </section>
      </fieldset><Button className="h-14 w-full text-lg" disabled={busy||!online||(!canReceive&&!!existing)} type="submit">{busy?"กำลังบันทึก...":locked?"ลองบันทึกเดิมอีกครั้ง":existing?"ยืนยันรับสินค้าเดิมเพิ่ม":"บันทึกสินค้าและสต๊อก"}</Button></form>}
    </>}
    <ProductBarcodeScanner open={scanning} onClose={()=>setScanning(false)} onScan={code=>{setScanning(false);void lookup(code);}}/>
  </div></main>;
}

export default function RetailProductIntakePage(): JSX.Element {
  const identity=useAuthStore(s=>`${s.companyId}:${s.brandId}:${s.branchId}:${s.user?.id}`);
  return <Workspace key={identity}/>;
}
