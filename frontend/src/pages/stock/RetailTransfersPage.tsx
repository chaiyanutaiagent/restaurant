import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useOnlineStatus } from "@/lib/syncService";
import { useAuthStore } from "@/stores/auth.store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Location = {id:string;name:string;branch_id:string;branch_name:string;is_warehouse:boolean};
type Stock = {product_id:string;variant_id:string|null;name:string;sku:string;available:string};
type Item = {id:string;product_name:string;sku:string;qty_requested:string;qty_approved:string|null;qty_sent:string|null;qty_received:string|null;qty_in_transit:string;qty_discrepancy:string};
type Order = {id:string;version:number;to_number:string;status:string;from_branch_id:string;to_branch_id:string;from_branch_name:string;to_branch_name:string;requested_by:string;note:string|null;discrepancy_note:string|null;items:Item[]};
type Pending = {url:string;body:Record<string,unknown>};
const root="/retail/transfers";
const statuses:Record<string,string>={draft:"ร่าง",pending_approval:"รออนุมัติ",approved:"อนุมัติแล้ว",in_transit:"ระหว่างทาง",partially_received:"รับบางส่วน",completed:"รับเสร็จ",cancelled:"ยกเลิก"};
const key=(row:Stock)=>`${row.product_id}:${row.variant_id??"base"}`;
const box="rounded-2xl border bg-white p-4 space-y-4";
const selectStyle="h-12 w-full rounded-lg border bg-white px-3";

type TransferProps = { embedded?: boolean; onNavigationLock?: (locked: boolean) => void };
function Workspace({embedded, onNavigationLock}: TransferProps) {
  const auth=useAuthStore();
  const online=useOnlineStatus();
  const cache=useQueryClient();
  const [page,setPage]=useState(1),[selected,setSelected]=useState("");
  const [creating,setCreating]=useState(false),[source,setSource]=useState(""),[dest,setDest]=useState(""),[search,setSearch]=useState("");
  const [lines,setLines]=useState<(Stock&{quantity:string})[]>([]);
  const [quantities,setQuantities]=useState<Record<string,string>>({});
  const [note,setNote]=useState(""),[finalize,setFinalize]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false);
  const pending=useRef<Pending|null>(null),inFlight=useRef(false);
  const locked=busy||uncertain;
  useEffect(()=>{onNavigationLock?.(locked);return()=>onNavigationLock?.(false);},[locked,onNavigationLock]);
  const canCreate=auth.hasPermission("inventory.transfer.create"),canApprove=auth.hasPermission("inventory.transfer.approve");
  const scope=["retail-transfers",auth.companyId,auth.brandId,auth.branchId];
  const get=async<T,>(path:string)=>(await api.get<{data:T}>(path)).data.data;
  const locations=useQuery({queryKey:[...scope,"options"],queryFn:()=>get<Location[]>(`${root}/options`)});
  const orders=useQuery({queryKey:[...scope,"list",page],queryFn:()=>get<{orders:Order[];has_more:boolean}>(`${root}?page=${page}`)});
  const detail=useQuery({queryKey:[...scope,"detail",selected],queryFn:()=>get<Order>(`${root}/${selected}`),enabled:!!selected});
  const stock=useQuery({queryKey:[...scope,"stock",source,search],queryFn:()=>get<Stock[]>(`${root}/stock?source_id=${source}&search=${encodeURIComponent(search)}`),enabled:creating&&!!source});
  const order=detail.data;
  const atSource=order?.from_branch_id===auth.branchId,atDest=order?.to_branch_id===auth.branchId;
  const receiving=!!order&&["in_transit","partially_received"].includes(order.status)&&atDest&&canCreate;
  const approving=order?.status==="pending_approval"&&atSource&&canApprove&&order.requested_by!==auth.user?.id;
  useEffect(()=>{setQuantities({});setNote("");setFinalize(false);},[selected,order?.version]);
  useEffect(()=>{if(!locked)return;const guard=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};window.addEventListener("beforeunload",guard);return()=>window.removeEventListener("beforeunload",guard);},[locked]);
  function message(e:unknown){const d=axios.isAxiosError(e)?e.response?.data?.detail:null;return typeof d==="string"?d:"ดำเนินการไม่สำเร็จ กรุณาตรวจข้อมูลและลองใหม่";}
  async function send(request?:Pending) {
    if(inFlight.current||!online)return;
    if(!pending.current)pending.current=request??null;
    if(!pending.current)return;
    inFlight.current=true;setBusy(true);setError("");setNotice("");
    try {
      const result=(await api.post<{data:Order}>(pending.current.url,pending.current.body)).data.data;
      pending.current=null;setUncertain(false);setCreating(false);setSelected(result.id);setLines([]);
      setNotice("บันทึกใบโอนเรียบร้อย");
      await cache.invalidateQueries({queryKey:scope});
      // A replay can contain an older snapshot; always reload the current order.
      await cache.invalidateQueries({queryKey:[...scope,"detail",result.id]});
    }catch(e){
      const status=axios.isAxiosError(e)?e.response?.status:undefined;
      if(status&&status>=400&&status<500){pending.current=null;setUncertain(false);setError(message(e));void cache.invalidateQueries({queryKey:scope});}
      else {setUncertain(true);setError("ยังยืนยันผลไม่ได้ กรุณาลองคำขอเดิมอีกครั้ง ระบบจะไม่เพิ่มหรือตัดสต๊อกซ้ำ อย่าออกจากหน้านี้");}
    }finally{inFlight.current=false;setBusy(false);}
  }
  function command(action:string){
    if(!order)return;
    const items=order.items.map(i=>({item_id:i.id,quantity:quantities[i.id]??(action==="approve"?i.qty_requested:(i.qty_received??"0"))}));
    if(action==="cancel"&&!note.trim()){setError("กรุณาระบุเหตุผลยกเลิกในหมายเหตุ");return;}
    if(action==="receive"&&finalize&&items.some((v,index)=>Number(v.quantity)<Number(order.items[index].qty_sent))&&!note.trim()){setError("กรุณาระบุเหตุผลสินค้าขาดก่อนปิดรับ");return;}
    void send({url:`${root}/${order.id}/commands`,body:{request_id:crypto.randomUUID(),expected_version:order.version,action,items:["approve","receive"].includes(action)?items:[],note,finalize:action==="receive"&&finalize}});
  }
  const options=locations.data??[];
  const validPair=options.some(l=>l.id===source&&l.branch_id===auth.branchId)||options.some(l=>l.id===dest&&l.branch_id===auth.branchId);
  return <main data-pos-touch-surface className="min-h-screen bg-slate-50 p-3 sm:p-6"><div className="mx-auto max-w-6xl space-y-4">
    <header className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm text-blue-700">Retail · บริษัท / แบรนด์ / สาขาที่เลือก</p><h1 className="text-2xl font-bold">โอนสินค้าคลังกลาง → ร้านค้า</h1></div>{!locked&&!embedded&&<Button variant="outline" asChild><Link to="/retail/pos">กลับหน้าขาย</Link></Button>}</header>
    <p className="text-sm text-slate-600">ร่าง → ส่งอนุมัติ → คลังอนุมัติและส่งออก → ร้านรับจริง จึงเพิ่มสต๊อกร้าน • เฉพาะคลัง Retail ในแบรนด์เดียวกัน ไม่เชื่อมครัวกลาง</p>
    {!online&&<p role="alert" className="rounded-xl bg-amber-100 p-3">ต้องออนไลน์เพื่อยืนยันรายการโอน</p>}
    {error&&<p role="alert" className="rounded-xl bg-red-50 p-3 text-red-700">{error}</p>}
    {notice&&<p role="status" className="rounded-xl bg-green-50 p-3">{notice}</p>}
    {uncertain&&<Button disabled={busy||!online} onClick={()=>void send()}>ลองคำขอเดิมอีกครั้ง</Button>}
    {(locations.isError||orders.isError||detail.isError)&&<p role="alert">โหลดข้อมูลไม่สำเร็จหรือไม่มีสิทธิ์ <Button variant="outline" disabled={locked||!online} onClick={()=>void cache.invalidateQueries({queryKey:scope})}>โหลดใหม่</Button></p>}
    <fieldset disabled={locked} className="min-w-0 space-y-4">
      <div className="flex flex-wrap gap-3"><Button variant="outline" disabled={!online} onClick={()=>void cache.invalidateQueries({queryKey:scope})}>รีเฟรช</Button>{canCreate&&<Button disabled={!online||!options.length} onClick={()=>{setCreating(true);setSelected("");setLines([]);setNote("");setError("");}}>+ สร้างใบโอน</Button>}</div>
      {locations.isLoading&&<p>กำลังโหลดคลังสินค้า…</p>}
      {locations.isSuccess&&(!options.some(l=>l.is_warehouse)||!options.some(l=>!l.is_warehouse))&&<p className="rounded-xl bg-amber-50 p-4">ให้ผู้ดูแลกำหนดสาขาคลังกลาง Retail และคลังหน้าร้าน แล้วผูกทั้งสองสาขากับแบรนด์เดียวกันก่อน ไม่ต้องโอนหากร้านรับสินค้าเอง</p>}
      {creating&&<form className={box} onSubmit={e=>{e.preventDefault();if(!lines.length||!validPair)return;void send({url:root,body:{request_id:crypto.randomUUID(),from_location_id:source,to_location_id:dest,note,items:lines.map(l=>({product_id:l.product_id,variant_id:l.variant_id,qty_requested:l.quantity}))}});}}>
        <h2 className="font-bold">สร้างใบโอนสินค้า</h2><div className="grid gap-3 md:grid-cols-2">
          <label>คลังต้นทาง<select aria-label="คลังต้นทาง" className={selectStyle} required value={source} onChange={e=>{setSource(e.target.value);setLines([]);}}><option value="">เลือกคลังกลาง Retail</option>{options.filter(l=>l.is_warehouse).map(l=><option key={l.id} value={l.id}>{l.branch_name} · {l.name}</option>)}</select></label>
          <label>คลังปลายทาง<select aria-label="คลังปลายทาง" className={selectStyle} required value={dest} onChange={e=>setDest(e.target.value)}><option value="">เลือกร้านค้า</option>{options.filter(l=>!l.is_warehouse).map(l=><option key={l.id} value={l.id}>{l.branch_name} · {l.name}</option>)}</select></label>
        </div>
        <label className="block">ค้นหาสินค้าต้นทาง<Input value={search} maxLength={150} onChange={e=>setSearch(e.target.value)} placeholder="ชื่อ / SKU / บาร์โค้ด (แสดงสูงสุด 100 รายการ)"/></label>
        {stock.isLoading&&source&&<p>กำลังโหลดสินค้า…</p>}{stock.isError&&<p role="alert">โหลดสินค้าคลังต้นทางไม่ได้ กรุณารีเฟรช</p>}
        {source&&stock.isSuccess&&!stock.data.length&&<p>ไม่พบสินค้าตามคำค้นในคลังต้นทาง</p>}
        <div className="grid max-h-64 gap-2 overflow-y-auto sm:grid-cols-2">{stock.data?.map(s=><Button key={key(s)} type="button" variant="outline" className="h-auto min-h-12 justify-start whitespace-normal text-left" disabled={lines.some(l=>key(l)===key(s))||Number(s.available)<=0||lines.length>=100} onClick={()=>setLines([...lines,{...s,quantity:"1"}])}>{s.name} · {s.sku} · พร้อมโอน {s.available}</Button>)}</div>
        {lines.map((l,index)=><div key={key(l)} className="flex flex-wrap items-end gap-3 rounded-xl bg-slate-50 p-3"><label className="min-w-0 flex-1">{l.name}<Input aria-label={`จำนวน ${l.sku}`} type="number" required min="0.0001" step="0.0001" max={l.available} value={l.quantity} onChange={e=>setLines(lines.map((v,i)=>i===index?{...v,quantity:e.target.value}:v))}/></label><Button type="button" variant="outline" onClick={()=>setLines(lines.filter((_,i)=>i!==index))}>นำออก</Button></div>)}
        <label className="block">หมายเหตุ<Input maxLength={1000} value={note} onChange={e=>setNote(e.target.value)}/></label>
        {!validPair&&source&&dest&&<p role="alert">เลือกต้นทางหรือปลายทางเป็นสาขาที่กำลังทำงานอยู่</p>}
        <Button type="submit" disabled={!online||!lines.length||!validPair}>บันทึกร่าง</Button> <Button type="button" variant="outline" onClick={()=>setCreating(false)}>ปิดแบบฟอร์ม</Button>
      </form>}
      <div className="grid items-start gap-4 lg:grid-cols-[320px_1fr]">
        <section className={box}><h2 className="font-bold">ใบโอนของสาขานี้</h2>{orders.isLoading&&<p>กำลังโหลด…</p>}{orders.isSuccess&&!orders.data.orders.length&&<p>ยังไม่มีใบโอน</p>}{orders.data?.orders.map(o=><button key={o.id} type="button" aria-pressed={selected===o.id} className={`w-full rounded-xl border p-3 text-left ${selected===o.id?"border-blue-500 bg-blue-50":""}`} onClick={()=>{setCreating(false);setSelected(o.id);setError("");}}><strong>{o.to_number}</strong><p>{statuses[o.status]??o.status}</p><p className="break-words text-sm">{o.from_branch_name} → {o.to_branch_name}</p></button>)}
          <div className="flex items-center gap-2"><Button variant="outline" disabled={page===1} onClick={()=>setPage(page-1)}>ก่อนหน้า</Button><span>{page}</span><Button variant="outline" disabled={!orders.data?.has_more} onClick={()=>setPage(page+1)}>ถัดไป</Button></div>
        </section>
        {selected&&detail.isLoading?<p>กำลังโหลดใบโอน…</p>:order&&!creating?<section className={box}><h2 className="text-xl font-bold">{order.to_number} · {statuses[order.status]??order.status}</h2><p>{order.from_branch_name} → {order.to_branch_name}</p>{order.note&&<p className="break-words">{order.note}</p>}
          {order.items.map(i=><div key={i.id} className="space-y-2 rounded-xl bg-slate-50 p-3"><strong>{i.product_name}</strong><p className="break-all text-sm">{i.sku}</p><p className="text-sm">ขอ {i.qty_requested} · อนุมัติ {i.qty_approved??0} · ส่ง {i.qty_sent??0} · รับแล้ว {i.qty_received??0}</p><p className="text-sm">ระหว่างทาง {i.qty_in_transit} · ส่วนต่าง {i.qty_discrepancy}</p>{(receiving||approving)&&<label className="block">{receiving?"ยอดรับสะสม (รวมที่รับก่อนหน้า)":"จำนวนอนุมัติ"}<Input aria-label={`${receiving?"ยอดรับสะสม":"จำนวนอนุมัติ"} ${i.sku}`} type="number" min={receiving?i.qty_received??"0":"0.0001"} max={receiving?i.qty_sent??"0":i.qty_requested} step="0.0001" value={quantities[i.id]??(receiving?i.qty_received??"0":i.qty_requested)} onChange={e=>setQuantities({...quantities,[i.id]:e.target.value})}/></label>}</div>)}
          {order.discrepancy_note&&<p role="status" className="bg-amber-50 p-3">ส่วนต่าง: {order.discrepancy_note} — ไม่เพิ่มสต๊อกหรือคืนต้นทางอัตโนมัติ</p>}
          {!["completed","cancelled"].includes(order.status)&&<label className="block">หมายเหตุ / เหตุผล<Input maxLength={1000} value={note} onChange={e=>setNote(e.target.value)}/></label>}
          {receiving&&<label className="flex items-center gap-3"><input type="checkbox" checked={finalize} onChange={e=>setFinalize(e.target.checked)}/>ปิดรับใบนี้ รวมถึงสินค้าที่ขาด (ต้องระบุเหตุผล)</label>}
          {order.status==="pending_approval"&&atSource&&order.requested_by===auth.user?.id&&<p>ผู้อนุมัติต้องเป็นคนละคนกับผู้สร้างใบโอน</p>}
          <div className="flex flex-wrap gap-3">{canCreate&&order.status==="draft"&&<Button disabled={!online} onClick={()=>command("submit")}>ส่งอนุมัติ</Button>}{approving&&<Button disabled={!online} onClick={()=>command("approve")}>อนุมัติและจองสินค้า</Button>}{canApprove&&atSource&&order.status==="approved"&&<Button disabled={!online} onClick={()=>command("ship")}>ยืนยันส่งออกจากคลัง</Button>}{receiving&&<Button disabled={!online} onClick={()=>command("receive")}>ยืนยันรับสินค้า</Button>}{canCreate&&["draft","pending_approval","approved"].includes(order.status)&&<Button variant="outline" disabled={!online} onClick={()=>command("cancel")}>ยกเลิกใบโอน</Button>}</div>
        </section>:!creating&&<p className="p-4 text-slate-500">เลือกใบโอนเพื่อดูรายละเอียดและดำเนินการตามสิทธิ์</p>}
      </div>
    </fieldset>
  </div></main>;
}

export default function RetailTransfersPage(props:TransferProps={}){const auth=useAuthStore();return <Workspace key={`${auth.companyId}:${auth.brandId}:${auth.branchId}`} {...props}/>;}
