import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Download } from "lucide-react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { stockCountApi } from "@/lib/stockCountApi";
import { formatThaiCurrency } from "@/lib/cartUtils";
import type { ApiResponse } from "@/types/api";
import type { VarianceReport } from "@/types/stockCount";

type Props = {
  sessionId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

export default function VarianceReportDialog({ sessionId, open, onOpenChange }: Props): JSX.Element {
  const { toast } = useToast();
  const [showMatched, setShowMatched] = useState(false);

  const reportQuery = useQuery({
    queryKey: ["stock-count", "variance-report", sessionId],
    enabled: open && Boolean(sessionId),
    queryFn: async () => {
      const response = await stockCountApi.getVarianceReport(sessionId ?? "");
      return response.data as ApiResponse<VarianceReport>;
    }
  });

  const report = reportQuery.data?.data;

  async function handleDownload(): Promise<void> {
    if (!sessionId || !report) {
      return;
    }
    try {
      const response = await stockCountApi.downloadVariancePdf(sessionId);
      downloadBlob(response.data as Blob, `variance_report_${report.session_number}.pdf`);
    } catch (error) {
      toast({
        title: "ดาวน์โหลดไม่สำเร็จ",
        description: error instanceof Error ? error.message : "กรุณาลองใหม่อีกครั้ง",
        variant: "destructive"
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>
            รายงานผลการนับสินค้า {report ? `— ${report.session_number}` : ""}
          </DialogTitle>
          {report ? (
            <p className="text-sm text-gray-500">
              คลัง: {report.location_name} | วันที่: {report.count_date_thai}
            </p>
          ) : null}
        </DialogHeader>

        {report ? (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                <p className="text-sm text-green-700">ตรง</p>
                <p className="mt-2 text-2xl font-semibold text-green-900">{report.items_matched}</p>
              </div>
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                <p className="text-sm text-blue-700">เกิน</p>
                <p className="mt-2 text-2xl font-semibold text-blue-900">{report.items_over}</p>
              </div>
              <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="text-sm text-red-700">ขาด</p>
                <p className="mt-2 text-2xl font-semibold text-red-900">{report.items_short}</p>
              </div>
              <div className="rounded-lg border border-orange-200 bg-orange-50 p-4">
                <p className="text-sm text-orange-700">มูลค่าผลต่าง</p>
                <p className="mt-2 text-2xl font-semibold text-orange-900">
                  {formatThaiCurrency(Number(report.total_variance_value))}
                </p>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-gray-200">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-left">
                  <tr>
                    <th className="px-4 py-3">สินค้า</th>
                    <th className="px-4 py-3 text-right">คาดไว้</th>
                    <th className="px-4 py-3 text-right">นับจริง</th>
                    <th className="px-4 py-3 text-right">ผลต่าง</th>
                    <th className="px-4 py-3 text-right">%</th>
                    <th className="px-4 py-3 text-right">มูลค่า</th>
                  </tr>
                </thead>
                <tbody>
                  {report.variances.map((item) => (
                    <tr
                      key={`${item.sku}-${item.product_name}`}
                      className={item.variance_qty < 0 ? "bg-red-50" : "bg-green-50"}
                    >
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">{item.product_name}</p>
                        <p className="font-mono text-xs text-gray-500">{item.sku}</p>
                      </td>
                      <td className="px-4 py-3 text-right">{item.expected_qty}</td>
                      <td className="px-4 py-3 text-right">{item.actual_qty}</td>
                      <td className="px-4 py-3 text-right">
                        <Badge variant={item.variance_qty < 0 ? "destructive" : "success"} className="ml-auto w-fit">
                          {item.variance_qty}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">{item.variance_pct}%</td>
                      <td className="px-4 py-3 text-right">{formatThaiCurrency(Math.abs(Number(item.variance_value)))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="rounded-lg border border-gray-200">
              <button
                type="button"
                className="flex w-full items-center justify-between px-4 py-3 text-left"
                onClick={() => setShowMatched((current) => !current)}
              >
                <span className="font-medium text-gray-900">
                  สินค้าที่ตรงกัน ({report.matched_items.length} รายการ)
                </span>
                {showMatched ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </button>
              {showMatched ? (
                <div className="space-y-2 border-t border-gray-200 px-4 py-3">
                  {report.matched_items.map((item) => (
                    <div key={`${item.sku}-${item.product_name}`} className="flex items-center justify-between text-sm">
                      <span>{item.product_name}</span>
                      <span className="text-green-700">✓ {item.actual_qty}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-gray-500">
            {reportQuery.isLoading ? "กำลังโหลดรายงาน..." : "ไม่พบข้อมูลรายงาน"}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            ปิด
          </Button>
          <Button onClick={() => void handleDownload()} disabled={!report}>
            <Download className="h-4 w-4" />
            ดาวน์โหลด PDF
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
