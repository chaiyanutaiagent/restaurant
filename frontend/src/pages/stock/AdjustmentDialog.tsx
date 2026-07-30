import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
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
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { productApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import type { ApiResponse } from "@/types/api";
import type { Product, ProductListItem } from "@/types/product";
import type { StockBalance, StockLocation } from "@/types/stock";

const schema = z.object({
  product_id: z.string().min(1, "กรุณาเลือกสินค้า"),
  variant_id: z.string().optional(),
  location_id: z.string().min(1, "กรุณาเลือกคลัง"),
  qty: z.coerce.number(),
  cost_per_unit: z.coerce.number().optional(),
  note: z.string().optional()
}).superRefine((values, ctx) => {
  if (values.qty < 0 && !values.note?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["note"],
      message: "กรุณาระบุหมายเหตุเมื่อปรับสต็อกติดลบ"
    });
  }
});

type FormValues = z.infer<typeof schema>;
type FormInput = z.input<typeof schema>;

type AdjustmentDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  productId?: string;
  locationId?: string;
  onSuccess: () => void;
};

export default function AdjustmentDialog({
  open,
  onOpenChange,
  productId,
  locationId,
  onSuccess
}: AdjustmentDialogProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const form = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      product_id: productId ?? "",
      variant_id: "",
      location_id: locationId ?? "",
      qty: 0,
      cost_per_unit: undefined,
      note: ""
    }
  });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", "all-for-stock"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 100 });
      return response.data as ApiResponse<ProductListItem[]>;
    }
  });

  const locationsQuery = useQuery({
    queryKey: ["stock", "locations"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const selectedProductId = form.watch("product_id");
  const selectedLocationId = form.watch("location_id");
  const adjustmentQty = form.watch("qty");

  const productDetailQuery = useQuery({
    queryKey: ["catalog", "product-detail-for-adjust", selectedProductId],
    enabled: Boolean(selectedProductId),
    queryFn: async () => {
      const response = await productApi.get(selectedProductId);
      return response.data as ApiResponse<Product>;
    }
  });

  const balancesQuery = useQuery({
    queryKey: ["stock", "product-balance-preview", selectedProductId],
    enabled: Boolean(selectedProductId),
    queryFn: async () => {
      const response = await stockApi.getProductStock(selectedProductId);
      return response.data as ApiResponse<StockBalance[]>;
    }
  });

  const currentBalance = useMemo(() => {
    const balances = balancesQuery.data?.data ?? [];
    return balances.find((item) => item.location_id === selectedLocationId);
  }, [balancesQuery.data, selectedLocationId]);

  const previewQty = Number(currentBalance?.qty_on_hand ?? 0) + Number(adjustmentQty ?? 0);

  async function submit(values: FormValues): Promise<void> {
    try {
      await stockApi.adjust({
        location_id: values.location_id,
        product_id: values.product_id,
        variant_id: values.variant_id || undefined,
        qty: values.qty,
        note: values.note || undefined,
        cost_per_unit: values.cost_per_unit
      });
      toast({ title: "ปรับสต็อกสำเร็จ" });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      onSuccess();
      onOpenChange(false);
      form.reset({
        product_id: productId ?? "",
        variant_id: "",
        location_id: locationId ?? "",
        qty: 0,
        cost_per_unit: undefined,
        note: ""
      });
    } catch (error) {
      toast({
        title: "ปรับสต็อกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  const variants = productDetailQuery.data?.data.variants ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>ปรับสต็อก</DialogTitle>
          <DialogDescription>เพิ่มหรือลดจำนวนคงเหลือของสินค้าในคลัง</DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={form.handleSubmit(submit)}>
          <div className="grid gap-2">
            <Label htmlFor="adjust-product">สินค้า</Label>
            <select
              id="adjust-product"
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              disabled={Boolean(productId)}
              {...form.register("product_id")}
            >
              <option value="">เลือกสินค้า</option>
              {(productsQuery.data?.data ?? []).map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name} ({product.sku})
                </option>
              ))}
            </select>
            {form.formState.errors.product_id ? (
              <p className="text-xs text-red-600">{form.formState.errors.product_id.message}</p>
            ) : null}
          </div>

          {variants.length > 0 ? (
            <div className="grid gap-2">
              <Label htmlFor="adjust-variant">Variant</Label>
              <select
                id="adjust-variant"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("variant_id")}
              >
                <option value="">สินค้าหลัก</option>
                {variants.map((variant) => (
                  <option key={variant.id} value={variant.id}>
                    {variant.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="grid gap-2">
            <Label htmlFor="adjust-location">คลัง / Location</Label>
            <select
              id="adjust-location"
              className="h-10 rounded-md border border-gray-300 px-3 text-sm"
              disabled={Boolean(locationId)}
              {...form.register("location_id")}
            >
              <option value="">เลือกคลัง</option>
              {(locationsQuery.data?.data ?? []).map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name} ({location.code})
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="adjust-qty">จำนวนปรับ</Label>
            <Input id="adjust-qty" type="number" step="0.01" {...form.register("qty")} />
            <p className="text-xs text-gray-500">สต็อกปัจจุบัน: {Number(currentBalance?.qty_on_hand ?? 0)}</p>
            <p className={`text-xs ${previewQty < 0 ? "text-red-600" : "text-gray-500"}`}>
              หลังปรับ: {previewQty}
            </p>
            {previewQty < 0 ? (
              <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                <AlertTriangle className="h-4 w-4" />
                จำนวนหลังปรับจะติดลบ ซึ่งระบบจะไม่อนุญาต
              </div>
            ) : null}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="adjust-cost">ต้นทุนต่อหน่วย</Label>
            <Input id="adjust-cost" type="number" step="0.01" {...form.register("cost_per_unit")} />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="adjust-note">หมายเหตุ</Label>
            <textarea
              id="adjust-note"
              className="min-h-[100px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              {...form.register("note")}
            />
            {form.formState.errors.note ? (
              <p className="text-xs text-red-600">{form.formState.errors.note.message}</p>
            ) : null}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              ยกเลิก
            </Button>
            <Button type="submit">บันทึก</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
