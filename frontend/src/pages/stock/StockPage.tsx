import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRightLeft,
  Building2,
  Globe2,
  Package,
  Pencil,
  Plus,
  Warehouse,
  XCircle
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { usePermission } from "@/hooks/usePermission";
import { branchApi } from "@/lib/adminApi";
import { stockApi } from "@/lib/stockApi";
import { syncStockBalances } from "@/lib/syncService";
import type { ApiResponse } from "@/types/api";
import type { StockBalance, StockLocation, StockLocationPayload, StockMovement, StockSummary } from "@/types/stock";
import AdjustmentDialog from "@/pages/stock/AdjustmentDialog";
import ReceiveDialog from "@/pages/stock/ReceiveDialog";
import StockLocationDialog from "@/pages/stock/StockLocationDialog";
import TransferDialog from "@/pages/stock/TransferDialog";

type StockFilter = "all" | "low" | "zero";

function formatBaht(value: number): string {
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(value);
}

function getStatus(balance: StockBalance): { label: string; variant: "success" | "secondary" | "destructive" } {
  const available = Number(balance.qty_available);
  const threshold = Number(balance.min_stock_qty ?? 0);
  if (available === 0) {
    return { label: "หมด", variant: "destructive" };
  }
  if (threshold > 0 && available <= threshold) {
    return { label: "ใกล้หมด", variant: "secondary" };
  }
  return { label: "ปกติ", variant: "success" };
}

function getMovementBadge(type: string): "success" | "default" | "secondary" | "destructive" | "outline" {
  if (type === "receive" || type === "opening") return "success";
  if (type === "sale" || type === "issue" || type === "transfer_out") return "default";
  if (type === "adjust") return "secondary";
  if (type === "transfer_in") return "outline";
  return "secondary";
}

function errorMessage(error: unknown): string {
  const responseDetail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof responseDetail === "string") return responseDetail;
  if (error instanceof Error) return error.message;
  return "เกิดข้อผิดพลาด กรุณาลองใหม่";
}

export default function StockPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const canAdjust = usePermission("inventory.stock.adjust");
  const canRequestAdjustment = usePermission("inventory.stock.adjust.request");
  const hasStockAccess = usePermission("inventory.stock.view");
  const canViewStock = hasStockAccess || canRequestAdjustment;
  const canSubmitAdjustment = canAdjust || canRequestAdjustment;
  const [activeTab, setActiveTab] = useState("overview");
  const [locationId, setLocationId] = useState("");
  const [stockFilter, setStockFilter] = useState<StockFilter>("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [movementType, setMovementType] = useState("");
  const [movementSearch, setMovementSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [locationDialogOpen, setLocationDialogOpen] = useState(false);
  const [editingLocation, setEditingLocation] = useState<StockLocation | null>(null);

  const locationsQuery = useQuery({
    queryKey: ["stock", "locations", "page"],
    queryFn: async () => {
      const response = await stockApi.listLocations();
      return response.data as ApiResponse<StockLocation[]>;
    }
  });

  const manageLocationsQuery = useQuery({
    queryKey: ["stock", "locations", "manage"],
    queryFn: async () => (await stockApi.listLocations(undefined, true)).data.data,
    enabled: canAdjust
  });

  const branchesQuery = useQuery({
    queryKey: ["admin", "branches", "stock-locations"],
    queryFn: async () => (await branchApi.list()).data.data,
    enabled: canAdjust
  });

  const balancesQuery = useQuery({
    queryKey: ["stock", "balances", locationId],
    queryFn: async () => {
      const response = await stockApi.listBalances({ location_id: locationId || undefined });
      return response.data as ApiResponse<StockBalance[]>;
    }
  });

  const summaryQuery = useQuery({
    queryKey: ["stock", "summary"],
    queryFn: async () => {
      const response = await stockApi.getSummary();
      return response.data as ApiResponse<StockSummary>;
    }
  });

  const movementsQuery = useQuery({
    queryKey: ["stock", "movements", movementType, dateFrom, dateTo],
    queryFn: async () => {
      const response = await stockApi.listMovements({
        movement_type: movementType || undefined,
        page: 1,
        limit: 200,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined
      });
      return response.data as ApiResponse<StockMovement[]>;
    }
  });

  async function refreshLocationQueries(): Promise<void> {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["stock"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-config-locations"] }),
      queryClient.invalidateQueries({ queryKey: ["restaurant-store-stock-locations"] }),
      queryClient.invalidateQueries({ queryKey: ["stock-cutover-preview"] })
    ]);
  }

  const saveLocationMutation = useMutation({
    mutationFn: async (payload: StockLocationPayload) => {
      if (editingLocation) {
        return stockApi.updateLocation(editingLocation.id, payload);
      }
      return stockApi.createLocation(payload);
    },
    onSuccess: async () => {
      await refreshLocationQueries();
      toast({ title: editingLocation ? "บันทึกการแก้ไขคลังแล้ว" : "สร้างคลังแล้ว" });
      setLocationDialogOpen(false);
      setEditingLocation(null);
    },
    onError: (error: unknown) => {
      toast({ title: "บันทึกคลังไม่สำเร็จ", description: errorMessage(error), variant: "destructive" });
    }
  });

  useEffect(() => {
    void syncStockBalances();
  }, []);

  const balances = balancesQuery.data?.data ?? [];
  const locations = locationsQuery.data?.data ?? [];
  const managedLocations = manageLocationsQuery.data ?? [];
  const branches = branchesQuery.data ?? [];
  const branchMap = useMemo(() => new Map(branches.map((branch) => [branch.id, branch])), [branches]);
  const summary = summaryQuery.data?.data ?? {
    total_skus: 0,
    total_value: 0,
    low_stock_count: 0,
    zero_stock_count: 0
  };

  const derivedSummary = useMemo(() => {
    if (!locationId) {
      return summary;
    }
    const totalSkus = balances.length;
    const totalValue = balances.reduce(
      (sum, item) => sum + Number(item.qty_on_hand) * Number(item.cost_per_unit),
      0
    );
    const lowStockCount = balances.filter((item) => {
      const threshold = Number(item.min_stock_qty ?? 0);
      return threshold > 0 && Number(item.qty_on_hand) <= threshold;
    }).length;
    const zeroStockCount = balances.filter((item) => Number(item.qty_on_hand) === 0).length;
    return {
      total_skus: totalSkus,
      total_value: totalValue,
      low_stock_count: lowStockCount,
      zero_stock_count: zeroStockCount
    };
  }, [balances, locationId, summary]);

  const filteredBalances = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    return balances.filter((item) => {
      if (stockFilter === "low") {
        const threshold = Number(item.min_stock_qty ?? 0);
        if (!(threshold > 0 && Number(item.qty_available) <= threshold)) {
          return false;
        }
      }
      if (stockFilter === "zero" && Number(item.qty_available) !== 0) {
        return false;
      }
      if (!normalized) {
        return true;
      }
      return [item.product_name, item.product_sku, item.variant_name ?? ""].some((value) =>
        value.toLowerCase().includes(normalized)
      );
    });
  }, [balances, search, stockFilter]);

  const paginatedBalances = filteredBalances.slice((page - 1) * 20, page * 20);
  const movementRows = (movementsQuery.data?.data ?? []).filter((item) => {
    const normalized = movementSearch.trim().toLowerCase();
    if (!normalized) {
      return true;
    }
    return [item.product_name, item.product_sku, item.variant_name ?? ""].some((value) =>
      value.toLowerCase().includes(normalized)
    );
  });

  async function refreshAll(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["stock"] });
    await syncStockBalances();
  }

  return (
    <div>
      <PageHeader
        title="คลังสินค้า"
        subtitle="จัดการสต็อกสินค้า"
        actions={
          <div className="flex flex-wrap gap-2">
            {canAdjust ? (
              <Button
                onClick={() => {
                  setEditingLocation(null);
                  setLocationDialogOpen(true);
                  setActiveTab("locations");
                }}
              >
                <Plus className="h-4 w-4" />
                เพิ่มคลัง
              </Button>
            ) : null}
            {canViewStock ? (
              <Button variant="outline" onClick={() => navigate("/stock/multi-branch")}>
                <Globe2 className="h-4 w-4" />
                ภาพรวมทุกสาขา
              </Button>
            ) : null}
          </div>
        }
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">ภาพรวม</TabsTrigger>
          <TabsTrigger value="list">รายการสต็อก</TabsTrigger>
          <TabsTrigger value="history">ประวัติการเคลื่อนไหว</TabsTrigger>
          {canAdjust ? <TabsTrigger value="locations">จัดการคลัง</TabsTrigger> : null}
        </TabsList>

        {activeTab !== "locations" ? <div className="mt-4 max-w-xs">
          <select
            className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
            value={locationId}
            onChange={(event) => setLocationId(event.target.value)}
          >
            <option value="">ทุกคลัง</option>
            {locations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name} ({location.code})
              </option>
            ))}
          </select>
        </div> : null}

        <TabsContent value="overview">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-500">จำนวน SKU ทั้งหมด</p>
                    <p className="mt-3 text-2xl font-semibold text-gray-900">{derivedSummary.total_skus}</p>
                  </div>
                  <div className="rounded-xl bg-blue-50 p-3 text-blue-600">
                    <Package className="h-5 w-5" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-500">มูลค่าสต็อกรวม</p>
                    <p className="mt-3 text-2xl font-semibold text-gray-900">{formatBaht(Number(derivedSummary.total_value))}</p>
                  </div>
                  <div className="rounded-xl bg-green-50 p-3 text-green-600">
                    <Warehouse className="h-5 w-5" />
                  </div>
                </div>
              </CardContent>
            </Card>

            <button
              type="button"
              className="text-left"
              onClick={() => {
                setStockFilter("low");
                setActiveTab("list");
              }}
            >
              <Card>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm text-gray-500">สต็อกต่ำกว่าเกณฑ์</p>
                      <p className="mt-3 text-2xl font-semibold text-gray-900">{derivedSummary.low_stock_count}</p>
                    </div>
                    <div className="rounded-xl bg-orange-50 p-3 text-orange-600">
                      <AlertTriangle className="h-5 w-5" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </button>

            <button
              type="button"
              className="text-left"
              onClick={() => {
                setStockFilter("zero");
                setActiveTab("list");
              }}
            >
              <Card>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-sm text-gray-500">สต็อกหมด</p>
                      <p className="mt-3 text-2xl font-semibold text-gray-900">{derivedSummary.zero_stock_count}</p>
                    </div>
                    <div className="rounded-xl bg-red-50 p-3 text-red-600">
                      <XCircle className="h-5 w-5" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </button>
          </div>
        </TabsContent>

        <TabsContent value="list">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="ค้นหาจากชื่อสินค้า หรือ SKU"
                  className="max-w-sm"
                />
                <div className="flex flex-wrap gap-2">
                  {canSubmitAdjustment ? (
                    <Button onClick={() => setAdjustOpen(true)}>ปรับสต็อก</Button>
                  ) : null}
                  {canAdjust ? (
                    <>
                      <Button variant="outline" onClick={() => setReceiveOpen(true)}>
                        <Plus className="h-4 w-4" />
                        รับสินค้า
                      </Button>
                      <Button variant="outline" onClick={() => setTransferOpen(true)}>
                        <ArrowRightLeft className="h-4 w-4" />
                        โอนย้าย
                      </Button>
                    </>
                  ) : null}
                </div>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>สินค้า</TableHead>
                    <TableHead>Variant</TableHead>
                    <TableHead>หน่วย</TableHead>
                    <TableHead>จำนวนคงเหลือ</TableHead>
                    <TableHead>จองแล้ว</TableHead>
                    <TableHead>พร้อมจ่าย</TableHead>
                    <TableHead>ต้นทุน/หน่วย</TableHead>
                    <TableHead>มูลค่ารวม</TableHead>
                    <TableHead>สถานะสต็อก</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedBalances.map((item) => {
                    const status = getStatus(item);
                    return (
                      <TableRow key={item.id}>
                        <TableCell>
                          <div>
                            <p className="font-medium text-gray-900">{item.product_name}</p>
                            <p className="font-mono text-xs text-gray-500">{item.product_sku}</p>
                          </div>
                        </TableCell>
                        <TableCell>{item.variant_name ?? "-"}</TableCell>
                        <TableCell>{item.unit_code ?? "-"}</TableCell>
                        <TableCell>{Number(item.qty_on_hand)}</TableCell>
                        <TableCell>{Number(item.qty_reserved)}</TableCell>
                        <TableCell>{Number(item.qty_available)}</TableCell>
                        <TableCell>{formatBaht(Number(item.cost_per_unit))}</TableCell>
                        <TableCell>{formatBaht(Number(item.qty_on_hand) * Number(item.cost_per_unit))}</TableCell>
                        <TableCell>
                          <Badge variant={status.variant}>{status.label}</Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              <div className="flex items-center justify-between text-sm text-gray-500">
                <span>ทั้งหมด {filteredBalances.length} รายการ</span>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((prev) => prev - 1)}>
                    ก่อนหน้า
                  </Button>
                  <span>หน้า {page}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page * 20 >= filteredBalances.length}
                    onClick={() => setPage((prev) => prev + 1)}
                  >
                    ถัดไป
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card>
            <CardContent className="space-y-4 p-4">
              <div className="grid gap-3 md:grid-cols-4">
                <Input
                  value={movementSearch}
                  onChange={(event) => setMovementSearch(event.target.value)}
                  placeholder="ค้นหาสินค้า"
                />
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={movementType}
                  onChange={(event) => setMovementType(event.target.value)}
                >
                  <option value="">ทุกประเภท</option>
                  <option value="receive">receive</option>
                  <option value="opening">opening</option>
                  <option value="adjust">adjust</option>
                  <option value="transfer_in">transfer_in</option>
                  <option value="transfer_out">transfer_out</option>
                </select>
                <Input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
                <Input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>วันที่</TableHead>
                    <TableHead>สินค้า</TableHead>
                    <TableHead>ประเภท</TableHead>
                    <TableHead>จำนวน</TableHead>
                    <TableHead>ก่อน</TableHead>
                    <TableHead>หลัง</TableHead>
                    <TableHead>หมายเหตุ</TableHead>
                    <TableHead>ผู้ดำเนินการ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {movementRows.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>{new Date(item.created_at).toLocaleString("th-TH")}</TableCell>
                      <TableCell>
                        <div>
                          <p className="font-medium text-gray-900">{item.product_name}</p>
                          <p className="font-mono text-xs text-gray-500">{item.product_sku}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getMovementBadge(item.movement_type)}>{item.movement_type}</Badge>
                      </TableCell>
                      <TableCell className={Number(item.qty) >= 0 ? "text-green-600" : "text-blue-700"}>
                        {Number(item.qty) > 0 ? "+" : ""}
                        {Number(item.qty)}
                      </TableCell>
                      <TableCell>{Number(item.qty_before)}</TableCell>
                      <TableCell>{Number(item.qty_after)}</TableCell>
                      <TableCell>{item.note ?? "-"}</TableCell>
                      <TableCell>{item.user_name ?? item.user_id}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {canAdjust ? (
          <TabsContent value="locations">
            <Card>
              <CardContent className="space-y-4 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="flex items-center gap-2 font-semibold text-gray-900">
                      <Building2 className="h-5 w-5 text-blue-600" />
                      คลังแยกตามสาขา
                    </h2>
                    <p className="mt-1 text-sm text-gray-500">สร้างคลัง RAW, READY และ STORE-STOCK ก่อนนำไปผูกกับแบรนด์</p>
                  </div>
                  <Button
                    onClick={() => {
                      setEditingLocation(null);
                      setLocationDialogOpen(true);
                    }}
                  >
                    <Plus className="h-4 w-4" />
                    เพิ่มคลัง
                  </Button>
                </div>

                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>สาขา</TableHead>
                      <TableHead>รหัสคลัง</TableHead>
                      <TableHead>ชื่อคลัง</TableHead>
                      <TableHead>รายละเอียด</TableHead>
                      <TableHead>สถานะ</TableHead>
                      <TableHead className="text-right">จัดการ</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {managedLocations.map((item) => {
                      const branch = branchMap.get(item.branch_id);
                      return (
                        <TableRow key={item.id} className={item.is_active ? "" : "bg-gray-50 text-gray-500"}>
                          <TableCell>
                            <p className="font-medium">{branch?.name ?? item.branch_id}</p>
                            <p className="text-xs text-gray-500">{branch?.code ?? "-"}</p>
                          </TableCell>
                          <TableCell><Badge variant="outline">{item.code}</Badge></TableCell>
                          <TableCell className="font-medium">{item.name}</TableCell>
                          <TableCell className="max-w-xs truncate">{item.description || "-"}</TableCell>
                          <TableCell>
                            <Badge variant={item.is_active ? "success" : "secondary"}>
                              {item.is_active ? "ใช้งาน" : "ปิดใช้งาน"}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setEditingLocation(item);
                                setLocationDialogOpen(true);
                              }}
                            >
                              <Pencil className="h-4 w-4" />
                              แก้ไข
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                    {!manageLocationsQuery.isLoading && managedLocations.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-10 text-center text-gray-500">ยังไม่มีคลังสินค้า</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>
        ) : null}
      </Tabs>

      <AdjustmentDialog open={adjustOpen} onOpenChange={setAdjustOpen} onSuccess={() => void refreshAll()} />
      <ReceiveDialog open={receiveOpen} onOpenChange={setReceiveOpen} onSuccess={() => void refreshAll()} />
      <TransferDialog open={transferOpen} onOpenChange={setTransferOpen} onSuccess={() => void refreshAll()} />
      <StockLocationDialog
        open={locationDialogOpen}
        onOpenChange={(open) => {
          setLocationDialogOpen(open);
          if (!open) setEditingLocation(null);
        }}
        branches={branches}
        location={editingLocation}
        isPending={saveLocationMutation.isPending}
        onSubmit={(payload) => saveLocationMutation.mutate(payload)}
      />
    </div>
  );
}
