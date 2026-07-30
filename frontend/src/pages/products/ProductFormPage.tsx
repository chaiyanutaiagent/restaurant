import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Package, Plus, Star, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { categoryApi, productApi, unitApi } from "@/lib/productApi";
import { stockApi } from "@/lib/stockApi";
import { syncProductCatalog } from "@/lib/syncService";
import type { ApiResponse } from "@/types/api";
import type {
  Category,
  Product,
  ProductImage,
  ProductType,
  ProductVariant,
  Unit,
  VatType
} from "@/types/product";
import type { StockBalance } from "@/types/stock";

type ProductFormValues = {
  name: string;
  name_en: string;
  sku: string;
  barcode: string;
  description: string;
  product_type: ProductType;
  category_id: string;
  unit_id: string;
  cost_price: number;
  selling_price: number;
  vat_type: VatType;
  vat_rate: number;
  weight_grams: number;
  min_stock_qty: number;
  is_for_sale: boolean;
  is_for_purchase: boolean;
  is_active: boolean;
};

type VariantDraft = {
  id?: string;
  sku: string;
  barcode: string;
  name: string;
  attributesText: string;
  selling_price: number;
  cost_price: number;
  sort_order: number;
  isNew?: boolean;
  markedForDelete?: boolean;
};

type LocalImageDraft = {
  file: File;
  preview: string;
  isPrimary: boolean;
};

function parseNumber(value: number | string | null | undefined): number {
  return Number(value ?? 0);
}

function flattenCategories(items: Category[]): Category[] {
  return items.flatMap((item) => [item, ...flattenCategories(item.children)]);
}

function generateSku(): string {
  return `SKU-${Date.now()}`;
}

function calculateVatSummary(price: number, vatType: VatType, vatRate: number): string[] {
  if (vatType === "exempt") {
    return ["ไม่มี VAT"];
  }
  if (vatType === "included") {
    const preVat = price * 100 / (100 + vatRate || 100);
    const vatAmount = price - preVat;
    return [
      `ราคาก่อน VAT: ฿${preVat.toFixed(2)}`,
      `VAT ${vatRate}%: ฿${vatAmount.toFixed(2)}`
    ];
  }
  const total = price + (price * vatRate) / 100;
  return [`ราคารวม VAT: ฿${total.toFixed(2)}`];
}

export default function ProductFormPage(): JSX.Element {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditMode = Boolean(id);
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [variants, setVariants] = useState<VariantDraft[]>([]);
  const [draftImages, setDraftImages] = useState<LocalImageDraft[]>([]);
  const [productImages, setProductImages] = useState<ProductImage[]>([]);
  const [saving, setSaving] = useState(false);

  const form = useForm<ProductFormValues>({
    defaultValues: {
      name: "",
      name_en: "",
      sku: "",
      barcode: "",
      description: "",
      product_type: "simple",
      category_id: "",
      unit_id: "",
      cost_price: 0,
      selling_price: 0,
      vat_type: "included",
      vat_rate: 7,
      weight_grams: 0,
      min_stock_qty: 0,
      is_for_sale: true,
      is_for_purchase: true,
      is_active: true
    }
  });

  const categoriesQuery = useQuery({
    queryKey: ["catalog", "categories", "flat"],
    queryFn: async () => {
      const response = await categoryApi.list(true);
      return response.data as ApiResponse<Category[]>;
    }
  });

  const unitsQuery = useQuery({
    queryKey: ["catalog", "units"],
    queryFn: async () => {
      const response = await unitApi.list();
      return response.data as ApiResponse<Unit[]>;
    }
  });

  const productQuery = useQuery({
    queryKey: ["catalog", "product", id],
    enabled: isEditMode,
    queryFn: async () => {
      const response = await productApi.get(id as string);
      return response.data as ApiResponse<Product>;
    }
  });

  const stockQuery = useQuery({
    queryKey: ["stock", "product", id],
    enabled: isEditMode,
    queryFn: async () => {
      const response = await stockApi.getProductStock(id as string);
      return response.data as ApiResponse<StockBalance[]>;
    }
  });

  useEffect(() => {
    if (!productQuery.data?.data) {
      return;
    }

    const product = productQuery.data.data;
    form.reset({
      name: product.name,
      name_en: product.name_en ?? "",
      sku: product.sku,
      barcode: product.barcode ?? "",
      description: product.description ?? "",
      product_type: product.product_type,
      category_id: product.category_id ?? "",
      unit_id: product.unit_id ?? "",
      cost_price: parseNumber(product.cost_price),
      selling_price: parseNumber(product.selling_price),
      vat_type: product.vat_type,
      vat_rate: parseNumber(product.vat_rate),
      weight_grams: product.weight_grams ?? 0,
      min_stock_qty: parseNumber(product.min_stock_qty),
      is_for_sale: product.is_for_sale,
      is_for_purchase: product.is_for_purchase,
      is_active: product.is_active
    });
    setVariants(
      product.variants.map((variant) => ({
        id: variant.id,
        sku: variant.sku,
        barcode: variant.barcode ?? "",
        name: variant.name,
        attributesText: JSON.stringify(variant.attributes ?? {}, null, 2),
        selling_price: parseNumber(variant.selling_price),
        cost_price: parseNumber(variant.cost_price),
        sort_order: variant.sort_order
      }))
    );
    setProductImages(product.images);
  }, [form, productQuery.data]);

  const categories = categoriesQuery.data?.data ?? [];
  const flatCategories = useMemo(() => flattenCategories(categories), [categories]);
  const units = unitsQuery.data?.data ?? [];
  const productType = form.watch("product_type");
  const sellingPrice = form.watch("selling_price");
  const vatType = form.watch("vat_type");
  const vatRate = form.watch("vat_rate");

  async function handleUploadFiles(files: FileList | null): Promise<void> {
    if (!files?.length) {
      return;
    }

    const selectedFiles = Array.from(files).slice(0, 5);
    if (isEditMode && id) {
      for (const [index, file] of selectedFiles.entries()) {
        await productApi.uploadImage(id, file, productImages.length === 0 && index === 0);
      }
      const refreshed = await productApi.get(id);
      setProductImages((refreshed.data as ApiResponse<Product>).data.images);
      return;
    }

    const nextDrafts = selectedFiles.map((file, index) => ({
      file,
      preview: URL.createObjectURL(file),
      isPrimary: draftImages.length === 0 && index === 0
    }));
    setDraftImages((prev) => [...prev, ...nextDrafts].slice(0, 5));
  }

  async function handleDeleteImage(imageId: string): Promise<void> {
    if (!id) {
      return;
    }
    await productApi.deleteImage(id, imageId);
    const refreshed = await productApi.get(id);
    setProductImages((refreshed.data as ApiResponse<Product>).data.images);
  }

  async function handleSetPrimaryImage(imageId: string): Promise<void> {
    if (!id) {
      return;
    }
    const response = await productApi.setPrimaryImage(id, imageId);
    setProductImages((response.data as ApiResponse<Product>).data.images);
  }

  function appendVariant(): void {
    setVariants((prev) => [
      ...prev,
      {
        sku: "",
        barcode: "",
        name: "",
        attributesText: "{}",
        selling_price: 0,
        cost_price: 0,
        sort_order: prev.length,
        isNew: true
      }
    ]);
  }

  function updateVariant(index: number, field: keyof VariantDraft, value: string | number): void {
    setVariants((prev) =>
      prev.map((variant, currentIndex) =>
        currentIndex === index ? { ...variant, [field]: value } : variant
      )
    );
  }

  function removeVariant(index: number): void {
    setVariants((prev) =>
      prev.flatMap((variant, currentIndex) => {
        if (currentIndex !== index) {
          return [variant];
        }
        if (variant.id) {
          return [{ ...variant, markedForDelete: true }];
        }
        return [];
      })
    );
  }

  async function submit(values: ProductFormValues): Promise<void> {
    setSaving(true);
    try {
      const payload = {
        ...values,
        category_id: values.category_id || null,
        unit_id: values.unit_id || null,
        name_en: values.name_en || null,
        barcode: values.barcode || null,
        description: values.description || null,
        weight_grams: values.weight_grams || null
      };

      const response = isEditMode && id
        ? await productApi.update(id, payload)
        : await productApi.create(payload);
      const product = (response.data as ApiResponse<Product>).data;

      for (const variant of variants) {
        if (variant.markedForDelete && variant.id) {
          await productApi.deleteVariant(product.id, variant.id);
          continue;
        }
        if (variant.markedForDelete) {
          continue;
        }

        const data = {
          product_id: product.id,
          sku: variant.sku,
          barcode: variant.barcode || null,
          name: variant.name,
          attributes: JSON.parse(variant.attributesText || "{}"),
          selling_price: variant.selling_price,
          cost_price: variant.cost_price,
          sort_order: variant.sort_order,
          is_active: true
        };

        if (variant.id) {
          await productApi.updateVariant(product.id, variant.id, data);
        } else {
          await productApi.addVariant(product.id, data);
        }
      }

      for (const [index, image] of draftImages.entries()) {
        await productApi.uploadImage(product.id, image.file, image.isPrimary || index === 0);
      }

      await queryClient.invalidateQueries({ queryKey: ["catalog", "products"] });
      await queryClient.invalidateQueries({ queryKey: ["catalog", "product"] });
      await syncProductCatalog();
      toast({ title: "บันทึกสินค้าเรียบร้อยแล้ว" });
      navigate("/products");
    } catch (error) {
      const message = error instanceof Error ? error.message : "ไม่สามารถบันทึกสินค้าได้";
      toast({
        title: "บันทึกสินค้าไม่สำเร็จ",
        description: message,
        variant: "destructive"
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="pb-28">
      <PageHeader
        title={isEditMode ? "แก้ไขสินค้า" : "เพิ่มสินค้า"}
        subtitle="จัดการข้อมูลสินค้า รูปภาพ และตัวเลือกการขาย"
      />

      <form className="space-y-6" onSubmit={form.handleSubmit(submit)}>
        <Card>
          <CardHeader>
            <CardTitle>ข้อมูลพื้นฐาน</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="name">ชื่อสินค้า (TH) *</Label>
              <Input id="name" {...form.register("name", { required: true })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="name_en">ชื่อสินค้า (EN)</Label>
              <Input id="name_en" {...form.register("name_en")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="sku">รหัสสินค้า (SKU) *</Label>
              <div className="flex gap-2">
                <Input id="sku" {...form.register("sku", { required: true })} />
                <Button type="button" variant="outline" onClick={() => form.setValue("sku", generateSku())}>
                  สร้างอัตโนมัติ
                </Button>
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="barcode">บาร์โค้ด</Label>
              <Input id="barcode" {...form.register("barcode")} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="product_type">ประเภทสินค้า</Label>
              <select
                id="product_type"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("product_type")}
              >
                <option value="simple">สินค้าปกติ</option>
                <option value="variant">สินค้ามี Variant</option>
                <option value="service">บริการ</option>
                <option value="bundle">ชุดสินค้า</option>
                <option value="menu_item">เมนูอาหาร/เครื่องดื่ม (F&amp;B)</option>
                <option value="raw_material">วัตถุดิบ (F&amp;B)</option>
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="category_id">หมวดหมู่</Label>
              <select
                id="category_id"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("category_id")}
              >
                <option value="">ไม่ระบุ</option>
                {flatCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="unit_id">หน่วยนับ</Label>
              <select
                id="unit_id"
                className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                {...form.register("unit_id")}
              >
                <option value="">ไม่ระบุ</option>
                {units.map((unit) => (
                  <option key={unit.id} value={unit.id}>
                    {unit.code} - {unit.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label htmlFor="description">รายละเอียด</Label>
              <textarea
                id="description"
                className="min-h-[120px] rounded-md border border-gray-300 px-3 py-2 text-sm"
                {...form.register("description")}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ราคาและภาษี</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label htmlFor="cost_price">ราคาทุน</Label>
                <Input id="cost_price" type="number" step="0.01" {...form.register("cost_price", { valueAsNumber: true })} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="selling_price">ราคาขาย *</Label>
                <Input
                  id="selling_price"
                  type="number"
                  step="0.01"
                  {...form.register("selling_price", { required: true, valueAsNumber: true })}
                />
              </div>
            </div>

            <div className="grid gap-3">
              <Label>ประเภท VAT</Label>
              <div className="flex flex-wrap gap-4">
                {[
                  { value: "included", label: "รวม VAT แล้ว" },
                  { value: "excluded", label: "แยก VAT" },
                  { value: "exempt", label: "ยกเว้น VAT" }
                ].map((item) => (
                  <label key={item.value} className="flex items-center gap-2 text-sm text-gray-700">
                    <input type="radio" value={item.value} {...form.register("vat_type")} />
                    {item.label}
                  </label>
                ))}
              </div>
            </div>

            <div className="grid gap-2 md:max-w-xs">
              <Label htmlFor="vat_rate">อัตรา VAT</Label>
              <Input
                id="vat_rate"
                type="number"
                step="0.01"
                disabled={vatType === "exempt"}
                {...form.register("vat_rate", { valueAsNumber: true })}
              />
            </div>

            <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-800">
              {calculateVatSummary(parseNumber(sellingPrice), vatType, parseNumber(vatRate)).map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>รูปภาพสินค้า</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-gray-50 px-6 py-10 text-center">
              <ImagePlus className="mb-3 h-8 w-8 text-gray-400" />
              <p className="text-sm font-medium text-gray-700">ลากไฟล์มาวางหรือคลิกเพื่ออัปโหลด</p>
              <p className="mt-1 text-xs text-gray-500">รองรับ JPG, PNG, WEBP ไม่เกิน 5MB</p>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="hidden"
                onChange={(event) => void handleUploadFiles(event.target.files)}
              />
            </label>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              {productImages.map((image) => (
                <div key={image.id} className="relative overflow-hidden rounded-xl border border-gray-200">
                  <img src={image.url} alt={image.filename} className="h-28 w-full object-cover" />
                  <div className="flex items-center justify-between gap-2 p-2">
                    <Button type="button" variant="ghost" size="sm" onClick={() => void handleSetPrimaryImage(image.id)}>
                      <Star className={`h-4 w-4 ${image.is_primary ? "fill-current text-amber-500" : ""}`} />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => void handleDeleteImage(image.id)}>
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                </div>
              ))}
              {draftImages.map((image, index) => (
                <div key={`${image.file.name}-${index}`} className="relative overflow-hidden rounded-xl border border-gray-200">
                  <img src={image.preview} alt={image.file.name} className="h-28 w-full object-cover" />
                  <div className="flex items-center justify-between gap-2 p-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setDraftImages((prev) =>
                          prev.map((item, currentIndex) => ({
                            ...item,
                            isPrimary: currentIndex === index
                          }))
                        )
                      }
                    >
                      <Star className={`h-4 w-4 ${image.isPrimary ? "fill-current text-amber-500" : ""}`} />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDraftImages((prev) => prev.filter((_, currentIndex) => currentIndex !== index))}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>ตั้งค่าเพิ่มเติม</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="weight_grams">น้ำหนัก (กรัม)</Label>
              <Input id="weight_grams" type="number" {...form.register("weight_grams", { valueAsNumber: true })} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="min_stock_qty">จุดสั่งซื้อขั้นต่ำ</Label>
              <Input id="min_stock_qty" type="number" step="0.01" {...form.register("min_stock_qty", { valueAsNumber: true })} />
            </div>

            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3">
              <Checkbox
                checked={form.watch("is_for_sale")}
                onCheckedChange={(checked: boolean | "indeterminate") =>
                  form.setValue("is_for_sale", checked === true)
                }
              />
              <span className="text-sm text-gray-700">สำหรับขาย</span>
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3">
              <Checkbox
                checked={form.watch("is_for_purchase")}
                onCheckedChange={(checked: boolean | "indeterminate") =>
                  form.setValue("is_for_purchase", checked === true)
                }
              />
              <span className="text-sm text-gray-700">สำหรับซื้อ</span>
            </label>
            <label className="flex items-center gap-3 rounded-lg border border-gray-200 px-4 py-3 md:col-span-2">
              <Checkbox
                checked={form.watch("is_active")}
                onCheckedChange={(checked: boolean | "indeterminate") =>
                  form.setValue("is_active", checked === true)
                }
              />
              <span className="text-sm text-gray-700">สถานะใช้งาน</span>
            </label>
          </CardContent>
        </Card>

        {productType === "variant" ? (
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>Variants</CardTitle>
              <Button type="button" variant="outline" size="sm" onClick={appendVariant}>
                <Plus className="h-4 w-4" />
                เพิ่ม Variant
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {variants.filter((variant) => !variant.markedForDelete).length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-center text-sm text-gray-500">
                  ยังไม่มี Variant
                </div>
              ) : null}

              {variants.map((variant, index) =>
                variant.markedForDelete ? null : (
                  <div key={variant.id ?? `draft-${index}`} className="grid gap-3 rounded-xl border border-gray-200 p-4">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline">Variant #{index + 1}</Badge>
                      <Button type="button" variant="ghost" size="sm" onClick={() => removeVariant(index)}>
                        <Trash2 className="h-4 w-4 text-red-600" />
                      </Button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <Input value={variant.sku} onChange={(event) => updateVariant(index, "sku", event.target.value)} placeholder="SKU" />
                      <Input value={variant.name} onChange={(event) => updateVariant(index, "name", event.target.value)} placeholder="ชื่อ Variant" />
                      <Input value={variant.barcode} onChange={(event) => updateVariant(index, "barcode", event.target.value)} placeholder="บาร์โค้ด" />
                      <Input
                        type="number"
                        step="0.01"
                        value={variant.selling_price}
                        onChange={(event) => updateVariant(index, "selling_price", Number(event.target.value))}
                        placeholder="ราคา"
                      />
                    </div>
                    <textarea
                      value={variant.attributesText}
                      onChange={(event) => updateVariant(index, "attributesText", event.target.value)}
                      className="min-h-[100px] rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
                      placeholder='{"color":"red","size":"XL"}'
                    />
                  </div>
                )
              )}
            </CardContent>
          </Card>
        ) : null}

        {isEditMode ? (
          <Card>
            <CardHeader>
              <CardTitle>สต็อกปัจจุบัน</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {(stockQuery.data?.data ?? []).length > 0 ? (
                <div className="space-y-3">
                  {(stockQuery.data?.data ?? []).map((item) => (
                    <div key={item.id} className="grid grid-cols-3 gap-3 rounded-lg border border-gray-200 px-4 py-3 text-sm">
                      <div>{item.location_name ?? item.location_id}</div>
                      <div>คงเหลือ: {Number(item.qty_on_hand)}</div>
                      <div>พร้อมจ่าย: {Number(item.qty_available)}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-gray-300 px-4 py-6 text-sm text-gray-500">
                  ยังไม่มีข้อมูลสต็อกสำหรับสินค้านี้
                </div>
              )}
              <Link to="/stock" className="text-sm font-medium text-blue-600">
                ดูประวัติสต็อก →
              </Link>
            </CardContent>
          </Card>
        ) : null}

        <div className="fixed bottom-0 left-0 right-0 border-t border-gray-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-4">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Package className="h-4 w-4" />
              {isEditMode ? "กำลังแก้ไขข้อมูลสินค้า" : "สร้างสินค้าใหม่"}
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" onClick={() => navigate("/products")}>
                ยกเลิก
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? "กำลังบันทึก..." : "บันทึก"}
              </Button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
