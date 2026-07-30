import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { integrationApi } from "@/lib/integrationApi";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const events = ["sale.created", "stock.low", "product.updated", "order.received"];

export default function CreateWebhookDialog({ open, onOpenChange }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);

  useEffect(() => {
    if (!open) {
      setName("");
      setUrl("");
      setSecret("");
      setSelectedEvents([]);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: async () => integrationApi.createWebhook({ name, url, events: selectedEvents, secret: secret || null }),
    onSuccess: async () => {
      toast({ title: "เพิ่ม Webhook แล้ว" });
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["integrations"] });
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่ม Webhook ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  function toggleEvent(eventName: string, checked: boolean): void {
    setSelectedEvents((current) => {
      if (checked) {
        return current.includes(eventName) ? current : [...current, eventName];
      }
      return current.filter((item) => item !== eventName);
    });
  }

  const validUrl = url.startsWith("https://");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>เพิ่ม Webhook</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>ชื่อ*</Label>
            <Input value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>URL*</Label>
            <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/webhook" />
            {url && !validUrl ? <p className="text-sm text-red-600">ต้องเป็น URL แบบ https://</p> : null}
          </div>
          <div className="space-y-3">
            <Label>Events</Label>
            {events.map((eventName) => (
              <label key={eventName} className="flex items-center gap-3 rounded-lg border p-3">
                <Checkbox
                  checked={selectedEvents.includes(eventName)}
                  onCheckedChange={(checked) => toggleEvent(eventName, checked === true)}
                />
                <span className="font-mono text-sm">{eventName}</span>
              </label>
            ))}
          </div>
          <div className="space-y-2">
            <Label>Secret</Label>
            <Input value={secret} onChange={(event) => setSecret(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !name.trim() || !validUrl || selectedEvents.length === 0}
          >
            {mutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
