import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
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
import type { StockLocation } from "@/types/stock";

const schema = z.object({
  location_id: z.string().min(1, "กรุณาเลือกคลัง"),
  note: z.string().optional(),
  reference_id: z.string().optional(),
  items: z
    .array(
      z.object({
        product_id: z.string().min(1, "กรุณาเลือกสินค้า"),
        variant_id: z.string().optional(),
        qty: z.coerce.number().positive("จำนวนต้องมากกว่า 0"),
        cost_per_unit: z.coerce.number().optional()
      })
    )
    .min(1, "ต้องมีอย่างน้อย 1 รายการ")
});

type FormValues = z.infer<typeof schema>;
type FormInput = z.input<typeof schema>;

type ReceiveDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
};

export default function ReceiveDialog({
  open,
  onOpenChange,
  onSuccess
}: ReceiveDialogProps): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const form = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      location_id: "",
      note: "",
      reference_id: "",
      items: [{ product_id: "", variant_id: "", qty: 1, cost_per_unit: 0 }]
    }
  });
  const fieldArray = useFieldArray({ control: form.control, name: "items" });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", "receive-select"],
    queryFn: async () => {
      const response = await productApi.list({ page: 1, limit: 100 });
      return response.data as ApiResponse<ProductListItem[]>;
    }
  });

  const productDetailsQuery = useQuery({
    queryKey: ["catalog", "products", "receive-details"],
    queryFn: async () => {
      const items = productsQuery.data?.data ?? [];
      const responses = await Promise.all(items.slice(0, 100).map((item) => productApi.get(item.id)));
      return responses.map((response) => (response.data as ApiResponse<Product>).data);
    },
    enabled: Boolean(productsQuery.data?.data.length)
  });

  const locationsQuery = useQuery({
    queryKey: ["stock", "locations", "receive"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const productMap = new Map((productDetailsQuery.data ?? []).map((item) => [item.id, item]));

  async function submit(values: FormValues): Promise<void> {
    try {
      await stockApi.receive({
        location_id: values.location_id,
        items: values.items.map((item) => ({
          product_id: item.product_id,
          variant_id: item.variant_id || undefined,
          qty: item.qty,
          cost_per_unit: item.cost_per_unit
        })),
        note: values.note || undefined,
        reference_id: values.reference_id || undefined,
        reference_type: values.reference_id ? "PurchaseOrder" : undefined
      });
      toast({ title: "รับสินค้าเข้าคลังสำเร็จ" });
      await queryClient.invalidateQueries({ queryKey: ["stock"] });
      onSuccess();
      onOpenChange(false);
      form.reset();
    } catch (error) {
      toast({
        title: "รับสินค้าไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>รับสินค้า</DialogTitle>
          <DialogDescription>บันทึกรับสินค้าเข้าคลังแบบหลายรายการ</DialogDescription>
        </DialogHeader>

        <form className="space-y-4" onSubmit={form.handleSubmit(submit)}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="receive-location">คลัง</Label>
              <select
                id="receive-location"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
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
              <Label htmlFor="receive-reference">เลขอ้างอิง</Label>
              <Input id="receive-reference" {...form.register("reference_id")} />
            </div>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="receive-note">หมายเหตุ</Label>
            <textarea
              id="receive-note"
              className="min-h-[90px] rounded-md border border-gray-300 px-3 py-2 text-sm"
              {...form.register("note")}
            />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-medium text-gray-900">รายการสินค้า</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => fieldArray.append({ product_id: "", variant_id: "", qty: 1, cost_per_unit: 0 })}
              >
                <Plus className="h-4 w-4" />
                เพิ่มสินค้า
              </Button>
            </div>

            {fieldArray.fields.map((field, index) => {
              const selectedProduct = productMap.get(form.watch(`items.${index}.product_id`));
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

                  <Input type="number" step="0.01" {...form.register(`items.${index}.qty`)} />
                  <div className="flex gap-2">
                    <Input type="number" step="0.01" {...form.register(`items.${index}.cost_per_unit`)} />
                    <Button type="button" variant="ghost" size="icon" onClick={() => fieldArray.remove(index)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                </div>
              );
            })}
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
