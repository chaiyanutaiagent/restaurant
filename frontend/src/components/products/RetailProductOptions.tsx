import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ApiResponse } from "@/types/api";

type Parent = {id:string;name:string;product_brand_name:string|null;option_names:string[];variants:{name:string;barcode:string|null}[]};
type Brand = {id:string;name:string};
export type RetailOptions = {mode:"simple"|"variant"|"append";productBrandId:string;parent:Parent|null;attributes:{key:string;value:string}[]};
export const emptyRetailOptions:RetailOptions = {mode:"simple",productBrandId:"",parent:null,attributes:[{key:"แบบ",value:""}]};

export default function RetailProductOptions({value,onChange,disabled,onBusyChange}:{value:RetailOptions;onChange:(value:RetailOptions)=>void;disabled:boolean;onBusyChange:(busy:boolean)=>void}) {
  const scope=useAuthStore(s=>`${s.companyId}:${s.brandId}:${s.branchId}`);
  const cache=useQueryClient();
  const [brandName,setBrandName]=useState("");
  const [search,setSearch]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [editGroups,setEditGroups]=useState(false);
  const brands=useQuery({queryKey:["retail-product-brands",scope],queryFn:async()=>(await api.get<ApiResponse<Brand[]>>("/products/retail/product-brands")).data.data});
  const parents=useQuery({queryKey:["retail-variant-parents",scope,search],enabled:value.mode==="append",queryFn:async()=>(await api.get<ApiResponse<Parent[]>>("/products/retail/variant-parents",{params:{search}})).data.data});
  async function createBrand(){
    if(!brandName.trim()||busy||disabled)return;
    setBusy(true);onBusyChange(true);setError("");
    try{
      const result=(await api.post<ApiResponse<Brand>>("/products/retail/product-brands",{name:brandName.trim()})).data.data;
      cache.setQueryData<Brand[]>(["retail-product-brands",scope],old=>[...(old??[]).filter(b=>b.id!==result.id),result]);
      onChange({...value,productBrandId:result.id});setBrandName("");
    }catch(e){setError(axios.isAxiosError(e)&&typeof e.response?.data?.detail==="string"?e.response.data.detail:"เพิ่มแบรนด์ไม่สำเร็จ ลองชื่อเดิมอีกครั้งได้โดยไม่สร้างซ้ำ");}
    finally{setBusy(false);onBusyChange(false);}
  }
  return <fieldset disabled={disabled||busy} className="min-w-0 space-y-3 rounded-xl border border-blue-100 bg-blue-50/50 p-3">
    <legend className="px-1 font-semibold">แบรนด์สินค้าและตัวเลือก</legend>
    <label className="block">รูปแบบสินค้า<select aria-label="รูปแบบสินค้า" className="mt-1 h-12 w-full rounded border bg-white px-3" value={value.mode} onChange={e=>{setEditGroups(false);onChange({...value,mode:e.target.value as RetailOptions["mode"],parent:null,attributes:[{key:"แบบ",value:""}]});}}>
      <option value="simple">สินค้าทั่วไป ไม่มีตัวเลือก</option><option value="variant">สินค้าใหม่ มีตัวเลือก</option><option value="append">เพิ่มแบบให้สินค้าหลักเดิม</option>
    </select></label>
    {value.mode!=="append"?<>
      <label className="block">แบรนด์สินค้า<select aria-label="แบรนด์สินค้า" className="mt-1 h-12 w-full rounded border bg-white px-3" value={value.productBrandId} onChange={e=>onChange({...value,productBrandId:e.target.value})}><option value="">ไม่ระบุแบรนด์</option>{brands.data?.map(b=><option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
      <p className="text-xs text-slate-600">เช่น เลย์ Nike — ไม่ใช่แบรนด์ร้านหรือบริษัท</p>
      <div className="flex flex-wrap gap-2"><Input aria-label="ชื่อแบรนด์สินค้าใหม่" className="min-w-0 flex-1" maxLength={150} placeholder="ชื่อแบรนด์ใหม่" value={brandName} onChange={e=>setBrandName(e.target.value)}/><Button type="button" variant="outline" disabled={!brandName.trim()||busy||disabled} onClick={()=>void createBrand()}>เพิ่มแบรนด์สินค้า</Button></div>
    </>:<>
      <label className="block">ค้นหาสินค้าหลัก<Input maxLength={150} value={search} onChange={e=>setSearch(e.target.value)}/></label>
      <label className="block">สินค้าหลัก<select aria-label="สินค้าหลัก" required className="mt-1 h-12 w-full rounded border bg-white px-3" value={value.parent?.id??""} onChange={e=>{const parent=parents.data?.find(p=>p.id===e.target.value)??null;onChange({...value,parent,attributes:parent?.option_names.length?parent.option_names.map(key=>({key,value:""})):[{key:"",value:""}]});}}><option value="">เลือกสินค้า (สูงสุด 50 รายการ ใช้ค้นหาเพื่อเจาะจง)</option>{parents.data?.map(p=><option key={p.id} value={p.id}>{p.name}{p.product_brand_name?` · ${p.product_brand_name}`:""}</option>)}</select></label>
      {value.parent&&<p className="break-words text-xs text-slate-600">แบบที่มีแล้ว: {value.parent.variants.map(v=>v.name).join(", ")||"ยังไม่มี"} · ใช้หมวด หน่วย ภาษี และแบรนด์ของสินค้าหลักเดิม</p>}
    </>}
    {value.mode!=="simple"&&<>
      <p className="text-sm">บันทึกทีละแบบที่ขายจริง เช่น สีดำ / M แต่ละแบบมีราคา บาร์โค้ด รูป และสต๊อกแยกกัน</p>
      {value.attributes.map((row,index)=><div key={index} className="min-w-0 space-y-2 rounded-lg border bg-white p-3">
        {editGroups&&!value.parent?.option_names.length&&<label className="block text-sm">ชื่อกลุ่ม (ไม่บังคับ)<Input aria-label={`ชื่อกลุ่มตัวเลือก ${index+1}`} placeholder={index===0?'แบบ':`ตัวเลือก ${index+1}`} maxLength={40} value={row.key} onChange={e=>onChange({...value,attributes:value.attributes.map((r,i)=>i===index?{...r,key:e.target.value}:r)})} onBlur={()=>{if(!row.key.trim())onChange({...value,attributes:value.attributes.map((r,i)=>i===index?{...r,key:index===0?'แบบ':`ตัวเลือก ${index+1}`}:r)});}}/></label>}
        <label className="block">{row.key||'ตัวเลือก'}<Input aria-label={`ค่าตัวเลือก ${index+1}`} placeholder="เช่น ซาวครีม / ดำ / M" required maxLength={80} value={row.value} onChange={e=>onChange({...value,attributes:value.attributes.map((r,i)=>i===index?{...r,value:e.target.value}:r)})}/></label>
      </div>)}
      {!value.parent?.option_names.length&&<div className="flex flex-wrap gap-2"><Button type="button" variant="outline" disabled={value.attributes.length>=5} onClick={()=>{let n=value.attributes.length+1;while(value.attributes.some(r=>r.key===`ตัวเลือก ${n}`))n++;onChange({...value,attributes:[...value.attributes,{key:`ตัวเลือก ${n}`,value:""}]});}}>+ เพิ่มตัวเลือก</Button><Button type="button" variant="ghost" onClick={()=>setEditGroups(!editGroups)}>{editGroups?'ซ่อนชื่อกลุ่ม':'กำหนดชื่อกลุ่ม'}</Button>{value.attributes.length>1&&<Button type="button" variant="outline" onClick={()=>onChange({...value,attributes:value.attributes.slice(0,-1)})}>ลบกลุ่มสุดท้าย</Button>}</div>}
    </>}
    {(brands.isError||parents.isError)&&<p role="alert" className="text-red-700">โหลดแบรนด์หรือสินค้าหลักไม่สำเร็จ กรุณาโหลดหน้าใหม่</p>}
    {error&&<p role="alert" className="text-red-700">{error}</p>}
  </fieldset>;
}
