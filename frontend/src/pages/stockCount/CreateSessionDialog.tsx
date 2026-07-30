import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { authApi, systemApi } from "@/lib/api";
import { productApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import { stockCountApi } from "@/lib/stockCountApi";
import type { ApiResponse } from "@/types/api";
import type { ProductListItem } from "@/types/product";
import type { StockLocation } from "@/types/stock";
import type { Branch, UserBranch } from "@/types/user";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => Promise<void> | void;
};

function todayValue(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function CreateSessionDialog({ open, onOpenChange, onCreated }: Props): JSX.Element {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);
  const [branchId, setBranchId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [countDate, setCountDate] = useState(todayValue());
  const [note, setNote] = useState("");
  const [productSearch, setProductSearch] = useState("");
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);

  const branchesQuery = useQuery({
    queryKey: ["stock-count", "branches", "dialog"],
    queryFn: async () => {
      try {
        const response = await systemApi.branches();
        return response.data as ApiResponse<Branch[]>;
      } catch {
        const fallback = await authApi.myBranches();
        return {
          data: fallback.data.data.map((item: UserBranch) => ({
            id: item.branch_id,
            company_id: "",
            code: item.branch_name,
            name: item.branch_name,
            name_en: null,
            is_warehouse: false,
            is_active: true,
            sort_order: 0
          })),
          meta: fallback.data.meta,
          error: fallback.data.error
        } satisfies ApiResponse<Branch[]>;
      }
    }
  });

  const locationsQuery = useQuery({
    queryKey: ["stock-count", "locations", "dialog"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const productsQuery = useQuery({
    queryKey: ["stock-count", "products", "dialog"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 200 });
      return response.data as ApiResponse<ProductListItem[]>;
    }
  });

  const branches = branchesQuery.data?.data ?? [];
  const locations = useMemo(
    () => (locationsQuery.data?.data ?? []).filter((item) => !branchId || item.branch_id === branchId),
    [branchId, locationsQuery.data?.data]
  );
  const products = useMemo(() => {
    const normalized = productSearch.trim().toLowerCase();
    return (productsQuery.data?.data ?? []).filter((item) => {
      if (!normalized) {
        return true;
      }
      return [item.name, item.sku, item.barcode ?? ""].some((value) => value.toLowerCase().includes(normalized));
    });
  }, [productSearch, productsQuery.data?.data]);

  async function handleSubmit(): Promise<void> {
    if (!branchId || !locationId) {
      toast({ title: "กรุณาเลือกสาขาและคลังสินค้า", variant: "destructive" });
      return;
    }

    setSubmitting(true);
    try {
      const response = await stockCountApi.createSession({
        branch_id: branchId,
        location_id: locationId,
        count_date: countDate || undefined,
        note: note || undefined,
        product_ids: selectedProductIds.length ? selectedProductIds : undefined
      });
      const session = (response.data as ApiResponse<import("@/types/stockCount").CountSession>).data;
      toast({ title: "สร้าง session แล้ว" });
      onOpenChange(false);
      if (onCreated) {
        await onCreated();
      }
      navigate(`/stock-count/${session.id}`);
    } catch (error) {
      toast({
        title: "สร้าง session ไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  }

  function toggleProduct(productId: string): void {
    setSelectedProductIds((current) =>
      current.includes(productId) ? current.filter((id) => id !== productId) : [...current, productId]
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>เริ่มนับสินค้า</DialogTitle>
          <DialogDescription>สร้าง Stock Count Session ใหม่</DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">สาขา*</label>
            <select
              className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
              value={branchId}
              onChange={(event) => {
                setBranchId(event.target.value);
                setLocationId("");
              }}
            >
              <option value="">เลือกสาขา</option>
              {branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">คลังสินค้า*</label>
            <select
              className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
              value={locationId}
              onChange={(event) => setLocationId(event.target.value)}
            >
              <option value="">เลือกคลังสินค้า</option>
              {locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name} ({location.code})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">วันที่นับ</label>
            <Input type="date" value={countDate} onChange={(event) => setCountDate(event.target.value)} />
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">นับเฉพาะสินค้า</label>
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
            <Input
              className="pl-9"
              value={productSearch}
              onChange={(event) => setProductSearch(event.target.value)}
              placeholder="ค้นหาสินค้าจากชื่อ, SKU, บาร์โค้ด"
            />
          </div>
          <p className="text-xs text-gray-500">ว่างไว้ = นับทุกรายการ</p>
          <div className="max-h-56 space-y-2 overflow-y-auto rounded-lg border border-gray-200 p-3">
            {products.map((product) => (
              <label key={product.id} className="flex items-start gap-3 rounded-md px-2 py-2 hover:bg-gray-50">
                <input
                  type="checkbox"
                  checked={selectedProductIds.includes(product.id)}
                  onChange={() => toggleProduct(product.id)}
                />
                <div>
                  <p className="font-medium text-gray-900">{product.name}</p>
                  <p className="font-mono text-xs text-gray-500">{product.sku}</p>
                </div>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">หมายเหตุ</label>
          <textarea
            className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="หมายเหตุเพิ่มเติม"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting}>
            {submitting ? "กำลังสร้าง..." : "สร้าง Session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
