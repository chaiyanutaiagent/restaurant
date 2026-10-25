import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { unitApi } from '@/lib/productApi';
import { useOnlineStatus } from '@/lib/syncService';
import { useAuthStore } from '@/stores/auth.store';
import type { Unit } from '@/types/product';

type Props = {open:boolean;onOpenChange:(open:boolean)=>void;onCreated:(unit:Unit)=>void;onPending:(pending:boolean)=>void};
const scope = () => {const s=useAuthStore.getState();return `${s.companyId}:${s.brandId}:${s.branchId}:${s.businessType}:${s.targetDatabase}`;};
const normalize = (s:string) => s.trim().replace(/\s+/g,' ').toLocaleLowerCase('th-TH');
export default function RetailUnitCreateDialog(props:Props) {
  const identity=useAuthStore(s=>`${s.companyId}:${s.brandId}:${s.branchId}:${s.businessType}:${s.targetDatabase}`);
  return <UnitForm key={identity} {...props} identity={identity}/>;
}
function UnitForm({open,onOpenChange,onCreated,onPending,identity}:Props & {identity:string}) {
  const online=useOnlineStatus();
  const [name,setName]=useState('');
  const [decimals,setDecimals]=useState('0');
  const [busy,setBusy]=useState(false);
  const [uncertain,setUncertain]=useState(false);
  const [error,setError]=useState('');
  const flight=useRef(false);
  const request=useRef<{name:string;code:string;decimal_places:number}|null>(null);
  useEffect(()=>{onPending(busy||uncertain);return()=>onPending(false);},[busy,uncertain,onPending]);
  function finish(unit:Unit) {
    if(identity!==scope())return;
    if(!unit.is_active)throw Error('หน่วยนี้ปิดใช้งานอยู่ ให้ผู้ดูแลตรวจสอบก่อน');
    onCreated(unit);request.current=null;setUncertain(false);setName('');setDecimals('0');setError('');onOpenChange(false);
  }
  async function save(event:React.FormEvent) {
    event.preventDefault();
    if(flight.current||!online)return;
    const s=useAuthStore.getState();
    if(identity!==scope()||s.businessType!=='retail_pos'||s.targetDatabase!=='retail_pos'||!s.hasPermission('inventory.product.create')){setError('ไม่มีสิทธิ์เพิ่มหน่วยสินค้าในบริบทนี้');return;}
    const clean=name.trim().replace(/\s+/g,' ');
    if(!clean){setError('กรุณาระบุชื่อหน่วย');return;}
    flight.current=true;setBusy(true);setError('');
    let submitted=false;
    try {
      const rows=(await unitApi.list()).data.data as Unit[];
      if(identity!==scope())return;
      const saved=request.current&&rows.find(u=>u.code===request.current?.code);
      const duplicate=rows.find(u=>normalize(u.name)===normalize(clean));
      if(saved||duplicate){finish((saved||duplicate)!);return;}
      request.current??={name:clean,code:`U${crypto.randomUUID().replace(/-/g,'').slice(0,16).toUpperCase()}`,decimal_places:Number(decimals)};
      submitted=true;
      finish((await unitApi.create({...request.current,is_active:true})).data.data as Unit);
    } catch(e) {
      const status=axios.isAxiosError(e)?e.response?.status:undefined;
      if(submitted&&(!status||status>=500||status===409)){setUncertain(true);setError('ยังยืนยันผลไม่ได้ กดตรวจผลอีกครั้ง ระบบจะตรวจหน่วยเดิมก่อนสร้างซ้ำ');}
      else {setError(axios.isAxiosError(e)?(typeof e.response?.data?.detail==='string'?e.response.data.detail:'ติดต่อระบบไม่ได้ กรุณาลองใหม่'):e instanceof Error?e.message:'เพิ่มหน่วยไม่สำเร็จ');if(!uncertain)request.current=null;}
    } finally {flight.current=false;setBusy(false);}
  }
  return <Dialog open={open} onOpenChange={next=>{if(!busy&&!uncertain){setError('');onOpenChange(next);}}}><DialogContent className="max-w-md">
    <DialogHeader><DialogTitle>เพิ่มหน่วยสินค้า</DialogTitle><DialogDescription>เช่น ชิ้น ถุง ขวด หรือกิโลกรัม หน่วยใช้ร่วมกันใน Retail ของบริษัทนี้ ถ้ามีชื่อเดิมจะเลือกใช้หน่วยนั้น โดยไม่แก้ความละเอียดเดิม</DialogDescription></DialogHeader>
    <form onSubmit={save} className="space-y-4">
      <label className="block">ชื่อหน่วยสินค้า<Input aria-label="ชื่อหน่วยสินค้าใหม่" required maxLength={100} value={name} disabled={busy||uncertain} onChange={e=>setName(e.target.value)} placeholder="เช่น ถุง"/></label>
      <label className="block">การนับจำนวน<select aria-label="การนับจำนวน" className="mt-1 h-12 w-full rounded border px-3" value={decimals} disabled={busy||uncertain} onChange={e=>setDecimals(e.target.value)}><option value="0">จำนวนเต็ม เช่น ชิ้น / ถุง / ขวด</option><option value="3">ทศนิยม 3 ตำแหน่ง เช่น กิโลกรัม / ลิตร</option></select></label>
      {!online&&<p role="alert">ต้องออนไลน์เพื่อเพิ่มหน่วยสินค้า</p>}
      {error&&<p role="alert" className="text-red-700">{error}</p>}
      <div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={busy||uncertain} onClick={()=>onOpenChange(false)}>ยกเลิก</Button><Button type="submit" disabled={busy||!online}>{busy?'กำลังตรวจสอบ…':uncertain?'ตรวจผลหน่วยอีกครั้ง':'บันทึกหน่วยและเลือกใช้'}</Button></div>
    </form>
  </DialogContent></Dialog>;
}
