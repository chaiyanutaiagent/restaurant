import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { integrationApi } from "@/lib/integrationApi";
import type { WebhookDelivery, WebhookEndpoint } from "@/types/integration";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  webhook: WebhookEndpoint | null;
};

function statusLabel(delivery: WebhookDelivery): { label: string; className: string } {
  if (delivery.delivered_at) return { label: "✓ delivered", className: "text-green-600" };
  if (delivery.next_retry_at) return { label: "⏳ pending retry", className: "text-amber-600" };
  if (delivery.failed_at) return { label: "✗ failed", className: "text-red-600" };
  return { label: "-", className: "text-gray-500" };
}

export default function DeliveriesDialog({ open, onOpenChange, webhook }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const deliveriesQuery = useQuery({
    queryKey: ["integrations", "deliveries", webhook?.id],
    enabled: open && Boolean(webhook?.id),
    queryFn: async () => (await integrationApi.getDeliveries(webhook!.id)).data.data as WebhookDelivery[]
  });

  const retryMutation = useMutation({
    mutationFn: async () => integrationApi.testWebhook(webhook!.id),
    onSuccess: async () => {
      toast({ title: "ส่ง test webhook แล้ว" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "deliveries", webhook?.id] });
      await queryClient.invalidateQueries({ queryKey: ["integrations", "webhooks"] });
    },
    onError: (error: Error) => {
      toast({ title: "ทดสอบใหม่ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{webhook?.name || "Deliveries"}</DialogTitle>
          <p className="text-sm text-gray-500">{webhook?.url}</p>
        </DialogHeader>
        <div className="flex justify-end">
          <Button onClick={() => retryMutation.mutate()} disabled={retryMutation.isPending || !webhook}>
            {retryMutation.isPending ? "กำลังส่ง..." : "ทดสอบอีกครั้ง"}
          </Button>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>วันที่</TableHead>
              <TableHead>Event Type</TableHead>
              <TableHead>HTTP Status</TableHead>
              <TableHead>สถานะ</TableHead>
              <TableHead>Retry ครั้งที่</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(deliveriesQuery.data ?? []).map((delivery) => {
              const status = statusLabel(delivery);
              return (
                <TableRow key={delivery.id}>
                  <TableCell>{new Date(delivery.created_at).toLocaleString("th-TH")}</TableCell>
                  <TableCell className="font-mono text-sm">{delivery.event_type}</TableCell>
                  <TableCell>{delivery.response_status ?? "-"}</TableCell>
                  <TableCell className={status.className}>{status.label}</TableCell>
                  <TableCell>{delivery.attempt_count}</TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </DialogContent>
    </Dialog>
  );
}
