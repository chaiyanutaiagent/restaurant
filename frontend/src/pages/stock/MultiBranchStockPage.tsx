import { useQuery } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatThaiCurrency } from "@/lib/cartUtils";
import { transferApi } from "@/lib/transferApi";
import type { ApiResponse } from "@/types/api";
import type { MultiBranchStockResponse } from "@/types/transfer";

export default function MultiBranchStockPage(): JSX.Element {
  const navigate = useNavigate();
  const summaryQuery = useQuery({
    queryKey: ["transfer", "multi-branch-stock"],
    queryFn: async () => {
      const response = await transferApi.multiBranchStock();
      return response.data as ApiResponse<MultiBranchStockResponse>;
    }
  });

  const summary = summaryQuery.data?.data ?? { branches: [], grand_total_value: 0, grand_low_stock_count: 0 };

  return (
    <div className="space-y-6">
      <PageHeader title="สต็อกทุกสาขา" subtitle="ภาพรวมสินค้าคงคลังแต่ละสาขา" />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-gray-500">มูลค่ารวมทุกสาขา</p>
            <p className="mt-3 text-2xl font-semibold text-gray-900">{formatThaiCurrency(Number(summary.grand_total_value))}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="text-sm text-gray-500">สต็อกต่ำ (ทุกสาขา)</p>
            <p className="mt-3 text-2xl font-semibold text-orange-600">{summary.grand_low_stock_count}</p>
          </CardContent>
        </Card>
      </div>

      {summaryQuery.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-56 w-full" />
          <Skeleton className="h-56 w-full" />
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {summary.branches.map((branch) => {
            const ratio = Number(summary.grand_total_value) > 0 ? (Number(branch.total_value) / Number(summary.grand_total_value)) * 100 : 0;
            return (
              <Card key={branch.branch_id}>
                <CardContent className="space-y-4 p-5">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-xl font-semibold text-gray-900">{branch.branch_name}</p>
                      <p className="text-sm text-gray-500">สรุปสต็อกของสาขา</p>
                    </div>
                    <div className="rounded-xl bg-blue-50 p-3 text-blue-600">
                      <Globe2 className="h-5 w-5" />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-lg bg-blue-50 p-3"><p className="text-xs text-gray-500">SKU ที่มีสต็อก</p><p className="mt-2 text-lg font-semibold text-blue-700">{branch.product_count}</p></div>
                    <div className="rounded-lg bg-gray-50 p-3"><p className="text-xs text-gray-500">คลังสินค้า</p><p className="mt-2 text-lg font-semibold text-gray-700">{branch.location_count}</p></div>
                    <div className="rounded-lg bg-green-50 p-3"><p className="text-xs text-gray-500">มูลค่าสต็อก</p><p className="mt-2 text-lg font-semibold text-green-700">{formatThaiCurrency(Number(branch.total_value))}</p></div>
                    <div className="rounded-lg bg-orange-50 p-3"><p className="text-xs text-gray-500">สต็อกต่ำ</p><p className="mt-2 text-lg font-semibold text-orange-700">{branch.low_stock_count}</p></div>
                  </div>

                  <div>
                    <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                      <span>สัดส่วนมูลค่าสต็อก</span>
                      <span>{ratio.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100">
                      <div className="h-2 rounded-full bg-blue-600" style={{ width: `${Math.min(ratio, 100)}%` }} />
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => navigate(`/stock?branch_id=${branch.branch_id}`)}>ดูสต็อก →</Button>
                    <Button variant="outline" onClick={() => navigate(`/transfer/orders/new?from_branch=${branch.branch_id}`)}>โอนย้าย →</Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
