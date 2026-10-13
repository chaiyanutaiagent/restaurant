import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useAuthStore } from "@/stores/auth.store";
import { useOnlineStatus } from "@/lib/syncService";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Row={product_id:string;variant_id:string|null;product_name:string;variant_name:string|null;sku:string;barcode:string|null;product_brand_name:string|null;active:boolean;on_hand:string;reserved:string;available:string;incoming:string;outgoing:string;sold:string;returned:string;net_quantity:string;line_subtotal:string;refund_amount:string};
type Report={rows:Row[];page:number;total:number;generated_at:string};
const today=()=>new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Bangkok",year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date());
const columns:[keyof Row,string][]=[["sku","SKU"],["product_name","สินค้า"],["product_brand_name","แบรนด์สินค้า"],["variant_name","ตัวเลือก"],["barcode","บาร์โค้ด"],["on_hand","คงเหลือปัจจุบัน"],["reserved","จอง"],["available","พร้อมขาย"],["incoming","กำลังรับโอน"],["outgoing","กำลังส่งโอน"],["sold","ขายในช่วงวัน"],["returned","คืนในช่วงวัน"],["net_quantity","จำนวนขายสุทธิ"],["line_subtotal","ยอดรายการก่อนส่วนลดท้ายบิล"],["refund_amount","เงินคืนสำเร็จ"]];
export default function RetailSkuReportPage(){
  const auth=useAuthStore(),online=useOnlineStatus();
  const [start,setStart]=useState(today),[end,setEnd]=useState(today),[search,setSearch]=useState(""),[page,setPage]=useState(1);
  const report=useQuery({queryKey:["retail-sku-report",auth.companyId,auth.brandId,auth.branchId,start,end,search,page],enabled:!!start&&!!end&&end>=start,
    queryFn:async()=>(await api.get<{data:Report}>("/retail/reports/skus",{params:{start,end,search,page}})).data.data});
  function exportCsv(){
    if(!report.data)return;
    const safe=(v:unknown)=>{let s=String(v??"");if(/^[\s]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
    const csv=[columns.map(([,name])=>safe(name)).join(","),...report.data.rows.map(r=>columns.map(([key])=>safe(r[key])).join(","))].join("\r\n");
    const url=URL.createObjectURL(new Blob(["\uFEFF",csv],{type:"text/csv;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=`retail-sku-${start}-${end}-page-${page}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <main className="min-h-screen bg-slate-50 p-3 sm:p-6"><div className="mx-auto max-w-7xl space-y-4">
    <header className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">รายงาน Retail แยก SKU / ตัวเลือก</h1><Button variant="outline" asChild><Link to="/retail/pos">กลับหน้าขาย</Link></Button></header>
    <p>เฉพาะบริษัท แบรนด์ และสาขาที่เลือก · สต๊อกเป็นยอดปัจจุบัน ไม่ใช่ยอดย้อนหลัง · ระหว่างทางยังไม่รวมยอดพร้อมขาย</p>
    <p className="text-sm text-slate-600">ยอดขายนับตามวันขาย ส่วนคืนสินค้านับตามวันคืนสำเร็จ (เวลาไทย) จึงอาจคืนบิลก่อนช่วงวันที่ได้ ยอดรายการคือยอดตามบิลก่อนส่วนลดท้ายบิล ไม่ใช่ยอดเงินรับสุทธิหรือเอกสารภาษี แบรนด์สินค้าและตัวเลือกใช้ข้อมูลจัดหมวดปัจจุบัน</p>
    <section className="grid gap-3 rounded-2xl border bg-white p-4 sm:grid-cols-2 lg:grid-cols-4"><label>จากวันที่<Input aria-label="จากวันที่" type="date" value={start} onChange={e=>{setStart(e.target.value);setPage(1);}}/></label><label>ถึงวันที่<Input aria-label="ถึงวันที่" type="date" min={start} value={end} onChange={e=>{setEnd(e.target.value);setPage(1);}}/></label><label className="sm:col-span-2">ค้นหาสินค้า / แบรนด์ / ตัวเลือก / บาร์โค้ด<Input maxLength={150} value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}}/></label></section>
    {!online&&<p role="alert" className="bg-amber-100 p-3">ออฟไลน์ ข้อมูลที่แสดงอาจไม่เป็นปัจจุบัน</p>}
    {report.isError&&<p role="alert" className="bg-red-50 p-3">โหลดรายงานไม่ได้ ตรวจสิทธิ์และเลือกช่วงวันที่ไม่เกิน 367 วัน <Button variant="outline" disabled={!online} onClick={()=>void report.refetch()}>ลองใหม่</Button></p>}
    {report.isFetching&&<p role="status">กำลังโหลดรายงาน…</p>}
    {report.data&&<><div className="flex flex-wrap items-center gap-3"><span>{report.data.total} SKU · อัปเดต {new Date(report.data.generated_at).toLocaleString("th-TH")}</span><Button variant="outline" disabled={!online||report.isFetching} onClick={()=>void report.refetch()}>รีเฟรช</Button><Button disabled={!online||report.isFetching||!report.data.rows.length} onClick={exportCsv}>ดาวน์โหลด CSV หน้านี้</Button></div>
      {!report.data.rows.length?<p className="rounded-xl bg-white p-5">ไม่พบสินค้าตามคำค้นในสาขานี้</p>:<div className="max-w-full overflow-x-auto rounded-xl border bg-white"><table className="min-w-[1800px] text-sm"><thead className="bg-slate-100"><tr>{columns.map(([key,label])=><th key={key} className="whitespace-nowrap p-3 text-left">{label}</th>)}</tr></thead><tbody>{report.data.rows.map(r=><tr key={`${r.product_id}:${r.variant_id}`} className="border-t">{columns.map(([key])=><td key={key} className={`p-3 ${key==="sku"?"min-w-[170px] max-w-[200px] break-all font-mono text-xs":key==="product_name"?"min-w-[180px]":key==="variant_name"||key==="product_brand_name"?"min-w-[130px]":"whitespace-nowrap"}`}>{String(r[key]??"—")}{key==="product_name"&&!r.active&&<span className="block text-amber-700">ปิดใช้งาน</span>}</td>)}</tr>)}</tbody></table></div>}
      <div className="flex items-center gap-3"><Button variant="outline" disabled={page===1} onClick={()=>setPage(page-1)}>ก่อนหน้า</Button><span>หน้า {page} · สูงสุด 100 SKU ต่อหน้า</span><Button variant="outline" disabled={page*100>=report.data.total} onClick={()=>setPage(page+1)}>ถัดไป</Button></div></>}
  </div></main>;
}
