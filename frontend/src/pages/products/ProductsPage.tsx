import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Package, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { categoryApi, productApi } from "@/lib/productApi";
import { syncProductCatalog, useOnlineStatus } from "@/lib/syncService";
import type { ApiResponse } from "@/types/api";
import type { Category, ProductListItem } from "@/types/product";

type ProductStatusFilter = "all" | "active" | "inactive";

function formatBaht(value: string | number): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(Number(value || 0));
}

function getVatLabel(vatType: ProductListItem["vat_type"]): string {
  if (vatType === "included") {
    return "รวม VAT";
  }
  if (vatType === "excluded") {
    return "แยก VAT";
  }
  return "ยกเว้น VAT";
}

function countProductsByCategory(items: ProductListItem[]): Record<string, number> {
  return items.reduce<Record<string, number>>((acc, item) => {
    if (item.category_id) {
      acc[item.category_id] = (acc[item.category_id] ?? 0) + 1;
    }
    return acc;
  }, {});
}

function CategoryNode({
  category,
  selectedCategoryId,
  onSelect,
  counts,
  depth = 0
}: {
  category: Category;
  selectedCategoryId: string | null;
  onSelect: (categoryId: string) => void;
  counts: Record<string, number>;
  depth?: number;
}): JSX.Element {
  const [open, setOpen] = useState(true);
  const hasChildren = category.children.length > 0;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => onSelect(category.id)}
        className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
          selectedCategoryId === category.id ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
        }`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
      >
        <span className="flex items-center gap-2">
          {hasChildren ? (
            <span
              onClick={(event) => {
                event.stopPropagation();
                setOpen((prev) => !prev);
              }}
              className="inline-flex h-5 w-5 items-center justify-center rounded border border-gray-200 text-xs"
            >
              {open ? "-" : "+"}
            </span>
          ) : (
            <span className="inline-block h-2 w-2 rounded-full bg-gray-300" />
          )}
          {category.name}
        </span>
        <Badge variant="outline">{counts[category.id] ?? 0}</Badge>
      </button>

      {hasChildren && open ? (
        <div className="space-y-2">
          {category.children.map((child) => (
            <CategoryNode
              key={child.id}
              category={child}
              selectedCategoryId={selectedCategoryId}
              onSelect={onSelect}
              counts={counts}
              depth={depth + 1}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function ProductsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const canCreate = usePermission("inventory.product.create");
  const canDelete = usePermission("inventory.product.delete");
  const isOnline = useOnlineStatus();

  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProductStatusFilter>("all");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 300);

    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  const categoriesQuery = useQuery({
    queryKey: ["catalog", "categories", "tree"],
    queryFn: async () => {
      const response = await categoryApi.list(true);
      return response.data as ApiResponse<Category[]>;
    }
  });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", page, search, selectedCategoryId, statusFilter],
    queryFn: async () => {
      const response = await productApi.list({
        page,
        limit: 20,
        search: search || undefined,
        category_id: selectedCategoryId ?? undefined,
        is_active:
          statusFilter === "all" ? undefined : statusFilter === "active"
      });
      return response.data as ApiResponse<ProductListItem[]>;
    }
  });

  useEffect(() => {
    if (productsQuery.isSuccess && isOnline) {
      void syncProductCatalog();
    }
  }, [isOnline, productsQuery.isSuccess]);

  const categories = categoriesQuery.data?.data ?? [];
  const products = productsQuery.data?.data ?? [];
  const total = productsQuery.data?.meta.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 20));
  const categoryCounts = countProductsByCategory(products);

  async function handleDelete(productId: string): Promise<void> {
    const confirmed = window.confirm("ต้องการลบสินค้านี้ใช่หรือไม่");
    if (!confirmed) {
      return;
    }

    try {
      await productApi.delete(productId);
      toast({ title: "ลบสินค้าแล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["catalog", "products"] });
      void syncProductCatalog();
    } catch {
      toast({
        title: "ลบสินค้าไม่สำเร็จ",
        description: "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <div>
      <PageHeader
        title="สินค้า"
        subtitle="จัดการรายการสินค้า"
        actions={
          canCreate ? (
            <Button onClick={() => navigate("/products/new")}>
              <Plus className="h-4 w-4" />
              เพิ่มสินค้า
            </Button>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          <CardContent className="space-y-4 p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-gray-900">หมวดหมู่สินค้า</p>
                <p className="text-xs text-gray-500">เลือกเพื่อกรองรายการ</p>
              </div>
            </div>

            {categoriesQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : (
              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setSelectedCategoryId(null)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                    selectedCategoryId === null ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50"
                  }`}
                >
                  <span>ทั้งหมด</span>
                  <Badge variant="outline">{total}</Badge>
                </button>
                {categories.map((category) => (
                  <CategoryNode
                    key={category.id}
                    category={category}
                    selectedCategoryId={selectedCategoryId}
                    onSelect={setSelectedCategoryId}
                    counts={categoryCounts}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div className="relative w-full md:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-gray-400" />
                <Input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="ค้นหาจากชื่อสินค้า, SKU, บาร์โค้ด"
                  className="pl-9"
                />
              </div>

              <div className="flex items-center gap-2">
                {(["all", "active", "inactive"] as ProductStatusFilter[]).map((filter) => (
                  <Button
                    key={filter}
                    variant={statusFilter === filter ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setStatusFilter(filter);
                      setPage(1);
                    }}
                  >
                    {filter === "all" ? "All" : filter === "active" ? "Active" : "Inactive"}
                  </Button>
                ))}
              </div>
            </div>

            {productsQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : products.length > 0 ? (
              <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>รูป</TableHead>
                      <TableHead>SKU</TableHead>
                      <TableHead>ชื่อสินค้า</TableHead>
                      <TableHead>หมวดหมู่</TableHead>
                      <TableHead className="text-right">ราคาขาย</TableHead>
                      <TableHead>VAT</TableHead>
                      <TableHead>สถานะ</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {products.map((product) => (
                      <TableRow key={product.id}>
                        <TableCell>
                          {product.image_url ? (
                            <img
                              src={product.image_url}
                              alt={product.name}
                              className="h-10 w-10 rounded-md object-cover"
                            />
                          ) : (
                            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-gray-100 text-gray-400">
                              <Package className="h-4 w-4" />
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <button
                            type="button"
                            className="font-mono text-xs text-gray-700"
                            onClick={() => void navigator.clipboard.writeText(product.sku)}
                          >
                            {product.sku}
                          </button>
                        </TableCell>
                        <TableCell className="font-medium text-gray-900">{product.name}</TableCell>
                        <TableCell>{product.category_id ?? "-"}</TableCell>
                        <TableCell className="text-right">{formatBaht(product.selling_price)}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{getVatLabel(product.vat_type)}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={product.is_active ? "success" : "secondary"}>
                            {product.is_active ? "Active" : "Inactive"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => navigate(`/products/${product.id}/edit`)}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            {canDelete ? (
                              <Button
                                variant="ghost"
                                size="icon"
                                className="text-red-600 hover:text-red-700"
                                onClick={() => void handleDelete(product.id)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            ) : null}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <div className="flex flex-col gap-3 border-t border-gray-100 pt-4 text-sm md:flex-row md:items-center md:justify-between">
                  <p className="text-gray-500">ทั้งหมด {total} รายการ</p>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((prev) => prev - 1)}>
                      ก่อนหน้า
                    </Button>
                    <span className="text-gray-500">
                      หน้า {page} / {totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((prev) => prev + 1)}
                    >
                      ถัดไป
                    </Button>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
                <div className="rounded-full bg-blue-50 p-4 text-blue-600">
                  <Package className="h-8 w-8" />
                </div>
                <p className="mt-4 text-lg font-semibold text-gray-900">ยังไม่มีสินค้า</p>
                <p className="mt-1 text-sm text-gray-500">เพิ่มสินค้าแรกเพื่อเริ่มต้นใช้งานคลังสินค้า</p>
                {canCreate ? (
                  <Button className="mt-4" onClick={() => navigate("/products/new")}>
                    เพิ่มสินค้าแรก
                  </Button>
                ) : null}
              </div>
            )}

            {!isOnline ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                ขณะนี้ออฟไลน์อยู่ หน้าจอนี้จะใช้ข้อมูลล่าสุดที่เคย sync ไว้เมื่อเชื่อมต่อกลับมา
              </div>
            ) : null}

            {productsQuery.isError ? (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                ไม่สามารถโหลดรายการสินค้าได้ในขณะนี้
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
