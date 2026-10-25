import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { db } from '@/lib/db';
import { categoryApi } from '@/lib/productApi';
import type { Category } from '@/types/product';
import { ArrowLeft, ArrowRight, Boxes, Clock3, FileText, Layers, MonitorCog, PackagePlus, Printer, ReceiptText, RefreshCw, ScanBarcode, Settings, Truck } from 'lucide-react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth.store';
import { useLogout } from '@/hooks/useAuth';
import { useOnlineStatus } from '@/lib/syncService';
import { nativeProduct } from '@/native-pos/config';
import { Button } from '@/components/ui/button';
import RetailCategoryCreateDialog from '@/components/products/RetailCategoryCreateDialog';
import RetailProductIntakePage from '@/pages/products/RetailProductIntakePage';
import RetailTransfersPage from '@/pages/stock/RetailTransfersPage';
import RetailSkuReportPage from '@/pages/reports/RetailSkuReportPage';
import { canOpenRetailSection, retailSection, retailSections, RetailWorkspaceFrame, type RetailSection } from './RetailWorkspaceNav';

export type RetailTask = 'intake' | 'receive' | 'transfer' | 'stock' | 'sku' | 'categories';
type Props = {
  section: RetailSection; task?: string | null; onTask: (task: RetailTask | null) => void;
  onNavigate: (path: string, label: string) => void;
  onBills?: () => void; onHeld?: () => void; onShift?: () => void; onDevice?: () => void;
  shiftNumber?: string; heldCount?: number;
  initialBarcode?: string;
  navigationLocked?: boolean; onNavigationLock?: (locked: boolean) => void;
};
export default function RetailWorkspaceHub(props: Props) {
  const { section, task, onTask, onNavigate } = props;
  const has = useAuthStore(state => state.hasPermission);
  const user = useAuthStore(state => state.user);
  const branchId = useAuthStore(state => state.branchId);
  const online = useOnlineStatus();
  const logout = useLogout('/login');
  const cache = useQueryClient();
  const [categoriesOpen, setCategoriesOpen] = useState(false);
  if (!canOpenRetailSection(section, has)) return <main className="p-6" role="alert">ไม่มีสิทธิ์เข้าถึงส่วนนี้ กรุณาติดต่อผู้ดูแลร้าน</main>;
  const taskView = section === 'products' && (task === 'intake' || task === 'receive') && has('inventory.product.create')
    ? <RetailProductIntakePage embedded initialBarcode={task==='intake'?props.initialBarcode:undefined} onNavigationLock={props.onNavigationLock} mode={task === 'receive' ? 'receive' : 'create'}/>
    : section === 'products' && task === 'transfer' && has('inventory.transfer.view') ? <RetailTransfersPage embedded onNavigationLock={props.onNavigationLock}/>
    : (section === 'products' || section === 'reports') && (task === 'sku' || task === 'stock') && has('pos.report.view') ? <RetailSkuReportPage embedded view={task === 'stock' ? 'stock' : 'sales'}/>
    : section === 'products' && task === 'categories' && has('inventory.product.create') ? <RetailCategories onCreate={()=>setCategoriesOpen(true)}/> : null;
  const cards: { title: string; description: string; icon: typeof Boxes; visible: boolean; action: () => void }[] = section === 'products' ? [
    {title:'เพิ่มสินค้า', description:'สแกนบาร์โค้ด กรอกราคา ตัวเลือก และรูปสินค้า', icon:ScanBarcode, visible:has('inventory.product.create'), action:()=>onTask('intake')},
    {title:'หมวดหมู่สินค้า', description:'เพิ่มหมวดสำหรับจัดกลุ่มและกรองสินค้าหน้าขาย', icon:Layers, visible:has('inventory.product.create'), action:()=>onTask('categories')},
    {title:'รับสต๊อกสินค้าเดิม', description:'เพิ่มจำนวนสินค้าเข้าคลัง โดยไม่เปลี่ยนราคาขายเดิม', icon:PackagePlus, visible:has('inventory.product.create') && ['inventory.stock.adjust','brand.store.stock.adjust'].some(has), action:()=>onTask('receive')},
    {title:'โอนสินค้าจากคลังกลาง', description:'ตรวจรายการโอนและรับเข้าคลังหน้าร้าน', icon:Truck, visible:has('inventory.transfer.view'), action:()=>onTask('transfer')},
    {title:'สินค้าและยอดคงเหลือ', description:'ดู SKU ตัวเลือก และจำนวนพร้อมขายของสาขานี้', icon:Boxes, visible:has('pos.report.view'), action:()=>onTask('stock')},
  ] : section === 'bills' ? [
    {title:props.shiftNumber ? 'ปิดกะและสรุปเงิน' : 'เปิดกะขาย', description:props.shiftNumber ? `กะ ${props.shiftNumber} · ตรวจเงินก่อนปิดกะ` : 'เลือกคลังและเงินทอนตั้งต้นก่อนเริ่มขาย', icon:Clock3, visible:!!props.onShift, action:()=>props.onShift?.()},
    {title:'ประวัติบิล / พิมพ์ซ้ำ', description:'ดูรายละเอียดบิล รวมถึงขอคืนหรือยกเลิกตามสิทธิ์', icon:ReceiptText, visible:has('pos.sale.view') && !!props.onBills, action:()=>props.onBills?.()},
    {title:`บิลพัก (${props.heldCount ?? 0})`, description:'เรียกบิลที่พักไว้กลับมาขายต่อ', icon:FileText, visible:has('pos.draft.view') && !!props.onHeld, action:()=>props.onHeld?.()},
  ] : section === 'reports' ? [
    {title:'รายงานขายตามสินค้า / SKU', description:'ยอดรายการขายและคืนสินค้า เลือกช่วงวันที่และส่งออก CSV', icon:FileText, visible:has('pos.report.view'), action:()=>onTask('sku')},
    {title:'รายงานสต๊อกปัจจุบัน', description:'คงเหลือ จอง พร้อมขาย และสินค้าระหว่างโอน', icon:Boxes, visible:has('pos.report.view'), action:()=>onTask('stock')},
  ] : [
    {title:'เครื่องขายและเครื่องพิมพ์', description:'ตรวจการจับคู่ ตั้งค่าพิมพ์ และทดสอบเครื่องพิมพ์', icon:Printer, visible:!!nativeProduct || !!props.onDevice, action:()=>nativeProduct ? onNavigate('/native/device','เครื่องขายและเครื่องพิมพ์') : props.onDevice?.()},
    {title:'การเชื่อมต่อและซิงก์', description:'ตรวจรายการค้างและผลจากเซิร์ฟเวอร์ก่อนทำซ้ำ', icon:RefreshCw, visible:has('pos.sale.create'), action:()=>onNavigate(nativeProduct ? '/native/device' : '/retail/offline-sync','การเชื่อมต่อและซิงก์')},
    {title:'อัปเดตแอป', description:'ตรวจรุ่นใหม่ เมื่อทำรายการหรือพักบิลเรียบร้อยแล้ว', icon:MonitorCog, visible:!!nativeProduct, action:()=>onNavigate('/native/device','อัปเดตแอป')},
    {title:'จัดการอุปกรณ์', description:'สร้างเครื่องขายและลิงก์จับคู่สำหรับสาขา', icon:MonitorCog, visible:!nativeProduct && has('system.device.view'), action:()=>onNavigate('/devices','จัดการอุปกรณ์')},
    {title:'ตั้งค่าใบเสร็จของสาขา', description:'สำหรับผู้จัดการที่มีสิทธิ์ตั้งค่าสาขา', icon:Settings, visible:!nativeProduct && !!branchId && ['system.branch.edit','system.company.edit'].some(has), action:()=>onNavigate(`/branches/${branchId}/settings`,'ตั้งค่าใบเสร็จ')},
  ];
  return <section data-retail-workspace={section} className="min-w-0 flex-1 bg-slate-50 pb-28 md:overflow-auto md:pb-8">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b bg-white p-4 md:px-8"><div><p className="text-xs font-semibold text-blue-700">Foodchainservice · Retail</p><h1 className="text-2xl font-bold text-slate-900">{retailSections.find(s=>s.id===section)?.label}</h1></div><div className="text-right text-sm"><p>{user?.display_name}</p><p className="text-slate-500">{user?.username} · {online ? 'ออนไลน์' : 'ออฟไลน์'}</p></div></header>
    {taskView ? <><div className="px-4 pt-4"><Button variant="outline" disabled={props.navigationLocked} onClick={()=>onTask(null)}><ArrowLeft className="mr-2 h-4 w-4"/>กลับเมนู{retailSections.find(s=>s.id===section)?.label}</Button>{props.navigationLocked && <p role="status" className="mt-2 text-amber-800">กำลังบันทึกหรือรอยืนยันผล กรุณาตรวจรายการเดิมให้เสร็จก่อนเปลี่ยนหน้า</p>}</div>{taskView}</> : <div className="mx-auto max-w-5xl p-4 md:p-8">
      <p className="mb-6 text-slate-500">{section === 'products' ? 'เพิ่มสินค้าและหมวดหมู่ หรือรับสต๊อก โดยไม่รบกวนหน้าขาย' : section === 'bills' ? 'เปิดกะ ดูบิล และตรวจยอดก่อนปิดร้าน' : section === 'reports' ? 'รายงานจากข้อมูลจริงของบริษัท แบรนด์ และสาขาที่เลือก' : 'ตั้งค่าอุปกรณ์และตรวจความพร้อมของเครื่องนี้'}</p>
      <div className="grid gap-4 sm:grid-cols-2">{cards.filter(c=>c.visible).map(card=><button type="button" key={card.title} onClick={card.action} className="flex min-h-32 items-start gap-4 rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-400 focus-visible:ring-2 focus-visible:ring-blue-600"><span className="rounded-xl bg-blue-50 p-3 text-blue-600"><card.icon className="h-6 w-6"/></span><span className="min-w-0 flex-1"><span className="block font-bold text-slate-900">{card.title}</span><span className="mt-2 block text-sm text-slate-500">{card.description}</span></span><ArrowRight className="mt-2 h-4 w-4 shrink-0 text-slate-400"/></button>)}</div>
      {section === 'settings' && <div className="mt-8 border-t pt-5"><p className="mb-3 text-sm text-slate-500">บัญชี {user?.username} · กรุณาทำรายการหรือพักบิลก่อนออกจากระบบ</p><Button variant="outline" onClick={()=>{if(window.confirm('ออกจากระบบ? กรุณาพักบิลหรือทำรายการให้เสร็จก่อน')) logout();}}>ออกจากระบบ</Button></div>}
    </div>}
    <RetailCategoryCreateDialog open={categoriesOpen} onOpenChange={setCategoriesOpen} onCreated={async category=>{
      await db.categories.put({...category,synced_at:Date.now()});
      await cache.invalidateQueries({queryKey:['pos','categories']});
      await cache.invalidateQueries({queryKey:['retail-intake']});
      await cache.invalidateQueries({queryKey:['retail-workspace-categories']});
    }}/>
  </section>;
}

// Non-cashier roles can use their permitted management tools without sale.create.
export function RetailWorkspacePage() {
  const { section: value } = useParams();
  const section = retailSection(value);
  const [task, setTask] = useState<RetailTask | null>(null);
  const [locked, setLocked] = useState(false);
  useEffect(()=>setTask(null),[section]);
  const navigate = useNavigate();
  const has = useAuthStore(state=>state.hasPermission);
  if ((section==='sale'||section==='bills')&&has('pos.sale.create')) return <Navigate to={`/retail/pos?workspace=${section}`} replace/>;
  return <RetailWorkspaceFrame section={section} disabled={locked}><RetailWorkspaceHub key={section} section={section} task={task} onTask={value=>{if(!locked)setTask(value);}} onNavigate={path=>navigate(path)} navigationLocked={locked} onNavigationLock={setLocked}/></RetailWorkspaceFrame>;
}

export function RetailManagementPage({task}:{task:'intake'|'transfer'}) {
  const [locked,setLocked]=useState(false);
  return <RetailWorkspaceFrame section="products" disabled={locked}>
    {task==='intake'?<RetailProductIntakePage onNavigationLock={setLocked}/>:<RetailTransfersPage onNavigationLock={setLocked}/>}
  </RetailWorkspaceFrame>;
}

function RetailCategories({onCreate}:{onCreate:()=>void}) {
  const {companyId,brandId,branchId}=useAuthStore();
  const online=useOnlineStatus();
  const categories=useQuery({queryKey:['retail-workspace-categories',companyId,brandId,branchId],queryFn:async()=>(await categoryApi.list()).data.data as Category[]});
  return <div className="mx-auto max-w-4xl space-y-4 p-4 md:p-8"><header className="flex items-center justify-between gap-3"><h2 className="text-xl font-bold">หมวดหมู่สินค้า</h2><Button disabled={!online} onClick={onCreate}>+ เพิ่มหมวดสินค้า</Button></header>
    {!online&&<p role="alert" className="rounded-xl bg-amber-50 p-3">ออฟไลน์ · ยังเพิ่มหมวดไม่ได้ ข้อมูลที่แสดงอาจไม่เป็นปัจจุบัน</p>}
    {categories.isPending&&<p role="status">กำลังโหลดหมวดสินค้า…</p>}
    {categories.isError&&<p role="alert">โหลดหมวดไม่ได้ <Button variant="outline" disabled={!online} onClick={()=>void categories.refetch()}>ลองใหม่</Button></p>}
    {categories.data&&<div className="divide-y rounded-2xl border bg-white">{categories.data.length?categories.data.map(c=><div key={c.id} className="flex justify-between gap-3 p-4"><span className="font-medium">{c.name}</span><span className="text-sm text-slate-500">{c.is_active?'ใช้งาน':'ปิดใช้งาน'}</span></div>):<p className="p-6 text-slate-500">ยังไม่มีหมวดสินค้า เริ่มสร้างหมวดแรกได้เลย</p>}</div>}
  </div>;
}
