import { useId, useRef, useState } from 'react';
import { authApi } from '@/lib/api';
import { recipeError, stockUnits } from '@/lib/recipeUnits';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import type { ProductListItem } from '@/types/product';

export type QuickMaterial = ProductListItem & { inventory_setup?: { zero_balances_created: number; mapping_created: boolean; stock_deferred: boolean } };
type Role = 'central_raw' | 'central_ready' | 'store_local';
export default function RecipeMaterialPicker({ materials, selectedId, selectedName, endpoint, role, companyKitchen, disabled, onSelect, onCreated }: {
  materials: ProductListItem[]; selectedId: string; selectedName: string; endpoint: string; role: Role;
  companyKitchen: boolean; disabled: boolean; onSelect: (product: ProductListItem) => void; onCreated: (product: QuickMaterial) => void;
}): JSX.Element {
  const id = useId();
  const [search, setSearch] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState({ name: '', unit: 'kg', cost: '0', sku: '', role });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const key = useRef(crypto.randomUUID());
  const chosen = useRef(false);
  const normalize = (value: string): string => value.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const matches = materials.filter(p => normalize(`${p.name} ${p.sku}`).includes(normalize(search))).slice(0, 12);
  const duplicates = materials.filter(p => normalize(p.name).includes(normalize(draft.name)) || (draft.sku && normalize(p.sku) === normalize(draft.sku))).slice(0, 5);
  const exact = materials.some(p => normalize(p.name) === normalize(draft.name) || (draft.sku && normalize(p.sku) === normalize(draft.sku)));
  const select = (product: ProductListItem): void => { setExpanded(false); setSearch(''); onSelect(product); };
  const change = (value: Partial<typeof draft>): void => { setDraft(prev => ({ ...prev, ...value })); key.current = crypto.randomUUID(); setError(''); };
  const create = async (): Promise<void> => {
    if (busyRef.current || disabled || exact) return;
    if (!draft.name.trim() || !Number.isFinite(Number(draft.cost)) || Number(draft.cost) < 0) {
      setError('กรุณาระบุชื่อและต้นทุนที่ไม่ติดลบ'); return;
    }
    busyRef.current = true; setBusy(true); setError('');
    try {
      const { data } = await authApi.post(endpoint, { name: draft.name.trim(), unit: draft.unit,
        cost_price: Number(draft.cost), sku: draft.sku.trim(), inventory_role: draft.role,
        idempotency_key: key.current, use_company_kitchen: companyKitchen });
      chosen.current = true;
      setOpen(false); setExpanded(false); setSearch(''); onCreated(data.data as QuickMaterial);
    } catch (failure) { setError(recipeError(failure)); }
    finally { busyRef.current = false; setBusy(false); }
  };
  return <div className="min-w-0 space-y-2">
    <Label htmlFor={id}>ค้นหาวัตถุดิบ</Label>
    <Input id={id} role="combobox" aria-expanded={expanded} aria-controls={`${id}-results`} autoComplete="off"
      disabled={disabled} placeholder={selectedName || 'พิมพ์ชื่อวัตถุดิบ'} value={search}
      onFocus={() => setExpanded(true)} onChange={e => { setSearch(e.target.value); setExpanded(true); }}
      onKeyDown={e => {
        if (e.key === 'Escape') setExpanded(false);
        if (e.key === 'Enter') { e.preventDefault(); if (expanded && matches[0]) select(matches[0]); }
      }} />
    {selectedId && <p className="text-sm font-semibold text-emerald-800">เลือกแล้ว: {selectedName}</p>}
    {expanded && !disabled && <div id={`${id}-results`} role="listbox" aria-label="วัตถุดิบที่ค้นพบ" className="max-h-56 overflow-y-auto rounded-xl border bg-white p-1 shadow-sm">
      {matches.map(p => <button type="button" role="option" aria-selected={p.id === selectedId} key={p.id} className="block min-h-11 w-full rounded-lg p-2 text-left text-sm hover:bg-orange-50 focus:bg-orange-50" onClick={() => select(p)}>{p.name} · {p.unit?.code ?? 'ไม่ระบุหน่วย'}</button>)}
      {!matches.length && <p className="p-2 text-sm text-slate-500">ไม่พบวัตถุดิบนี้</p>}
      {search.trim() && <Button type="button" variant="outline" className="mt-1 w-full" onClick={() => {
        setDraft({ name: search.trim(), unit: 'kg', cost: '0', sku: '', role }); setError(''); key.current = crypto.randomUUID(); chosen.current = false; setOpen(true);
      }}>สร้างวัตถุดิบใหม่</Button>}
    </div>}
    <Dialog open={open} onOpenChange={next => { if (!busyRef.current) setOpen(next); }}>
      <DialogContent onCloseAutoFocus={event => { if (chosen.current) event.preventDefault(); }}>
        <DialogHeader><DialogTitle>สร้างวัตถุดิบใหม่</DialogTitle><DialogDescription>สร้างแล้วเลือกเข้าแถวสูตรนี้ทันที ข้อมูลสูตรที่กรอกไว้ไม่หาย</DialogDescription></DialogHeader>
        <div className="space-y-4" onKeyDown={e => { if (e.key === 'Enter' && e.target instanceof HTMLInputElement) { e.preventDefault(); void create(); } }}>
          <Label htmlFor={`${id}-name`}>ชื่อวัตถุดิบ<Input id={`${id}-name`} disabled={busy} value={draft.name} onChange={e => change({ name: e.target.value })} /></Label>
          {draft.name.trim() && duplicates.length > 0 && <div className="rounded-lg bg-amber-50 p-3 text-sm"><p>มีรายการใกล้เคียง เลือกใช้แทนการสร้างซ้ำได้</p>{duplicates.map(p => <button type="button" disabled={busy} className="block min-h-11 text-left font-bold underline" key={p.id} onClick={() => { chosen.current = true; setOpen(false); select(p); }}>{p.name}</button>)}</div>}
          <div className="grid grid-cols-2 gap-3">
            <Label htmlFor={`${id}-unit`}>หน่วยสต็อก<select id={`${id}-unit`} className="mt-1 h-11 w-full rounded-lg border px-2" disabled={busy} value={draft.unit} onChange={e => change({ unit: e.target.value })}>{stockUnits.map(u => <option key={u.value} value={u.value}>{u.label}</option>)}</select></Label>
            <Label htmlFor={`${id}-cost`}>ต้นทุนต่อ {draft.unit}<Input id={`${id}-cost`} type="number" min="0" step="0.0001" disabled={busy} value={draft.cost} onChange={e => change({ cost: e.target.value })} /></Label>
          </div>
          <details><summary className="cursor-pointer py-2 text-sm">ตั้งค่าเพิ่มเติม</summary><div className="space-y-3 py-2">
            <Label htmlFor={`${id}-sku`}>รหัสสินค้า (SKU) — เว้นว่างให้ระบบสร้าง<Input id={`${id}-sku`} maxLength={100} disabled={busy} value={draft.sku} onChange={e => change({ sku: e.target.value })} /></Label>
            {!companyKitchen && role !== 'central_raw' && <Label htmlFor={`${id}-role`}>แหล่งวัตถุดิบ<select id={`${id}-role`} className="h-11 w-full rounded-lg border" disabled={busy} value={draft.role} onChange={e => change({ role: e.target.value as Role })}><option value="central_ready">ส่วนกลางเตรียมให้</option><option value="store_local">ร้านซื้อเอง</option></select></Label>}
          </div></details>
          <p className="text-xs text-slate-500">สร้างรายการวัตถุดิบเท่านั้น ไม่รับสินค้าเข้าหรือเพิ่มยอดคงเหลือ</p>
          {error && <p role="alert" className="text-sm text-red-700">{error} — ข้อมูลที่กรอกยังอยู่</p>}
          <div className="flex justify-end gap-2"><Button type="button" variant="outline" disabled={busy} onClick={() => setOpen(false)}>ยกเลิก</Button><Button type="button" disabled={busy || exact || !draft.name.trim()} onClick={() => void create()}>{busy ? 'กำลังสร้าง…' : 'สร้างและเลือกใช้'}</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  </div>;
}
