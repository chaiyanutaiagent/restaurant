import { useState, type ReactNode } from 'react';
import { BarChart3, Boxes, MoreHorizontal, ReceiptText, Settings, ShoppingCart } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth.store';

export type RetailSection = 'sale' | 'products' | 'bills' | 'reports' | 'settings';
export const retailSections = [
  { id: 'sale', label: 'ขาย', icon: ShoppingCart },
  { id: 'products', label: 'สินค้าและสต๊อก', icon: Boxes },
  { id: 'bills', label: 'บิลและกะ', icon: ReceiptText },
  { id: 'reports', label: 'รายงาน', icon: BarChart3 },
  { id: 'settings', label: 'ตั้งค่า', icon: Settings },
] as const;
export function retailSection(value: string | null | undefined): RetailSection {
  return retailSections.find(section => section.id === value)?.id ?? 'sale';
}
export function canOpenRetailSection(id: RetailSection, has: (permission: string) => boolean): boolean {
  if (id === 'sale' || id === 'bills') return has('pos.sale.create');
  if (id === 'products') return ['inventory.product.create', 'inventory.transfer.view', 'pos.report.view'].some(has);
  if (id === 'reports') return has('pos.report.view');
  return true;
}
export default function RetailWorkspaceNav({ active, onSelect, disabled = false }: {
  active: RetailSection; onSelect?: (section: RetailSection) => void; disabled?: boolean;
}) {
  const navigate = useNavigate();
  const has = useAuthStore(state => state.hasPermission);
  const [more, setMore] = useState(false);
  const items = retailSections.filter(section => canOpenRetailSection(section.id, has));
  function select(section: RetailSection) {
    setMore(false);
    if (onSelect) onSelect(section);
    else navigate(has('pos.sale.create') ? `/retail/pos?workspace=${section}` : `/retail/workspace/${section}`);
  }
  const button = (item: typeof retailSections[number]) => <button key={item.id} type="button"
    disabled={disabled} aria-current={active === item.id ? 'page' : undefined} onClick={() => select(item.id)}
    className={`flex min-h-14 min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 text-xs font-semibold transition focus-visible:ring-2 focus-visible:ring-blue-600 disabled:opacity-50 md:w-full md:flex-none md:flex-row md:justify-start md:gap-3 md:px-4 md:text-sm ${active === item.id ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-blue-50'}`}>
    <item.icon className="h-5 w-5 shrink-0" aria-hidden="true"/><span>{item.label}</span>
  </button>;
  return <nav aria-label="เมนูหลัก Retail" data-retail-workspace-nav className="fixed inset-x-0 bottom-0 z-40 border-t bg-white p-2 md:sticky md:top-0 md:h-screen md:w-48 md:shrink-0 md:border-r md:border-t-0 md:p-3" style={{paddingBottom:'max(8px, env(safe-area-inset-bottom))'}}>
    <div className="mb-8 mt-4 hidden px-3 md:block"><p className="font-bold text-blue-700">Foodchainservice</p><p className="mt-1 text-xs text-slate-500">Retail POS</p></div>
    <div className="hidden space-y-2 md:block">{items.map(button)}</div>
    {more && <div className="absolute bottom-full left-2 right-2 mb-2 rounded-2xl border bg-white p-3 shadow-lg md:hidden"><p className="px-3 pb-2 text-sm font-semibold">เพิ่มเติม</p><div className="flex gap-2">{items.filter(i => i.id === 'reports' || i.id === 'settings').map(button)}</div></div>}
    <div className="flex gap-1 md:hidden">{items.filter(i => ['sale','products','bills'].includes(i.id)).map(button)}<button type="button" disabled={disabled} aria-expanded={more} onClick={() => setMore(!more)} className={`flex min-h-14 flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 text-xs font-semibold ${['reports','settings'].includes(active) ? 'bg-blue-600 text-white' : 'text-slate-600'}`}><MoreHorizontal className="h-5 w-5"/>เพิ่มเติม</button></div>
  </nav>;
}

export function RetailWorkspaceFrame({ section, children, disabled = false }: { section: RetailSection; children: ReactNode; disabled?: boolean }) {
  return <div className="flex min-h-screen bg-slate-50 pb-24 md:pb-0"><RetailWorkspaceNav active={section} disabled={disabled}/><div className="min-w-0 flex-1">{children}</div></div>;
}
