import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { useFieldArray, useForm } from "react-hook-form";
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
  from_location_id: z.string().min(1, "กรุณาเลือกคลังต้นทาง"),
  to_location_id: z.string().min(1, "กรุณาเลือกคลังปลายทาง"),
  note: z.string().optional(),
  items: z
    .array(
      z.object({
        product_id: z.string().min(1, "กรุณาเลือกสินค้า"),
        variant_id: z.string().optional(),
        qty: z.coerce.number().positive("จำนวนต้องมากกว่า 0")
      })
    )
    .min(1, "ต้องมีอย่างน้อย 1 รายการ")
}).superRefine((values, ctx) => {
  if (values.from_location_id === values.to_location_id) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["to_location_id"],
      message: "คลังต้นทางและปลายทางต้องไม่ซ้ำกัน"
    });
  }
});

type FormValues = z.infer<typeof schema>;
type FormInput = z.input<typeof schema>;

type TransferDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
};

export default function TransferDialog({
  open,
  onOpenChange,
  onSuccess
}: TransferDialogProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const form = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      from_location_id: "",
      to_location_id: "",
      note: "",
      items: [{ product_id: "", variant_id: "", qty: 1 }]
    }
  });
  const fieldArray = useFieldArray({ control: form.control, name: "items" });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", "transfer-select"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 100 });
      return response.data as ApiResponse<ProductListItem[]>;
    }
  });

  const productDetailsQuery = useQuery({
    queryKey: ["catalog", "products", "transfer-details"],
    queryFn: async () => {
      const items = productsQuery.data?.data ?? [];
      const responses = await Promise.all(items.slice(0, 100).map((item) => productApi.get(item.id)));
      return responses.map((response) => (response.data as ApiResponse<Product>).data);
    },
    enabled: Boolean(productsQuery.data?.data.length)
  });

  const locationsQuery = useQuery({
    queryKey: ["stock", "locations", "transfer"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const sourceLocationId = form.watch("from_location_id");
  const sourceBalancesQuery = useQuery({
    queryKey: ["stock", "balances", "source-location", sourceLocationId],
    enabled: Boolean(sourceLocationId),
    queryFn: async () => {
      const response = await stockApi.listBalances({ location_id: sourceLocationId });
      return response.data as ApiResponse<StockBalance[]>;
    }
  });

  const balanceMap = new Map(
    (sourceBalancesQuery.data?.data ?? []).map((item) => [`${item.product_id}:${item.variant_id ?? "base"}`, item])
  );
  const productMap = new Map((productDetailsQuery.data ?? []).map((item) => [item.id, item]));

  async function submit(values: FormValues): Promise<void> {
    try {
      await stockApi.transfer({
        from_location_id: values.from_location_id,
        to_location_id: values.to_location_id,
        items: values.items.map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id || undefined,
          qty: item.qty
        })),
        note: values.note || undefined
      });
      toast({ title: "โอนย้ายสต็อกสำเร็จ" });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      onSuccess();
      onOpenChange(false);
      form.reset();
    } catch (error) {
      toast({
        title: "โอนย้ายสต็อกไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>โอนย้ายสต็อก</DialogTitle>
          <DialogDescription>ย้ายสินค้าระหว่างคลังต้นทางและปลายทาง</DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={form.handleSubmit(submit)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="transfer-from">คลังต้นทาง</Label>
              <select
                id="transfer-from"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("from_location_id")}
              >
                <option value="">เลือกคลังต้นทาง</option>
                {(locationsQuery.data?.data ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name} ({location.code})
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="transfer-to">คลังปลายทาง</Label>
              <select
                id="transfer-to"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("to_location_id")}
              >
                <option value="">เลือกคลังปลายทาง</option>
                {(locationsQuery.data?.data ?? []).map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name} ({location.code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-medium text-gray-900">รายการโอน</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fieldArray.append({ product_id: "", variant_id: "", qty: 1 })}
              >
                <Plus className="h-4 w-4" />
                เพิ่มสินค้า
              </Button>
            </div>

            {fieldArray.fields.map((field, index) => {
              const selectedProduct = productMap.get(form.watch(`items.${index}.product_id`));
              const key = `${form.watch(`items.${index}.product_id`)}:${form.watch(`items.${index}.variant_id`) || "base"}`;
              const balance = balanceMap.get(key);
              const requestedQty = Number(form.watch(`items.${index}.qty`) || 0);
              const availableQty = Number(balance?.qty_available ?? 0);
              return (
                <div key={field.id} className="grid gap-3 rounded-xl border border-gray-200 p-4 md:grid-cols-4">
                  <select
                    className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                    {...form.register(`items.${index}.product_id`)}
                  >
                    <option value="">เลือกสินค้า</option>
                    {(productsQuery.data?.data ?? []).map((product) => (
                      <option key={product.id} value={product.id}>
                        {product.name} ({product.sku})
                      </option>
                    ))}
                  </select>

                  <select
                    className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                    {...form.register(`items.${index}.variant_id`)}
                  >
                    <option value="">สินค้าหลัก</option>
                    {(selectedProduct?.variants ?? []).map((variant) => (
                      <option key={variant.id} value={variant.id}>
                        {variant.name}
                      </option>
                    ))}
                  </select>

                  <div className="grid gap-1">
                    <Input type="number" step="0.01" {...form.register(`items.${index}.qty`)} />
                    <p className="text-xs text-gray-500">คงเหลือ: {availableQty}</p>
                  </div>

                  <div className="flex items-start gap-2">
                    <Button type="button" variant="ghost" size="icon" onClick={() => fieldArray.remove(index)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                    {requestedQty > availableQty ? (
                      <div className="flex items-center gap-1 text-xs text-red-600">
                        <AlertTriangle className="h-4 w-4" />
                        เกินคงเหลือ
                      </div>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="grid gap-2">
            <Label htmlFor="transfer-note">หมายเหตุ</Label>
            <textarea
              id="transfer-note"
              className="min-h-[90px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              {...form.register("note")}
            />
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
