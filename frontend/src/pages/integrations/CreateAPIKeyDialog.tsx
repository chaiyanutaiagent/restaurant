import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { integrationApi } from "@/lib/integrationApi";
import type { APIKeyCreated } from "@/types/integration";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const scopeOptions = [
  { value: "products:read", label: "products:read", description: "อ่านข้อมูลสินค้า" },
  { value: "orders:read", label: "orders:read", description: "อ่านออเดอร์" },
  { value: "orders:write", label: "orders:write", description: "รับออเดอร์จากเว็บ" },
  { value: "*", label: "*", description: "ทุกสิทธิ์ - admin only" }
];

export default function CreateAPIKeyDialog({ open, onOpenChange }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [scopes, setScopes] = useState<string[]>(["products:read", "orders:write"]);
  const [created, setCreated] = useState<APIKeyCreated | null>(null);

  useEffect(() => {
    if (!open) {
      setName("");
      setExpiresAt("");
      setScopes(["products:read", "orders:write"]);
      setCreated(null);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: async () =>
      integrationApi.createApiKey({
        name,
        scopes,
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined
      }),
    onSuccess: async (response) => {
      setCreated(response.data.data as APIKeyCreated);
      await queryClient.invalidateQueries({ queryKey: ["integrations"] });
    },
    onError: (error: Error) => {
      toast({ title: "สร้าง API Key ไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  function toggleScope(scope: string, checked: boolean): void {
    setScopes((current) => {
      if (checked) {
        return current.includes(scope) ? current : [...current, scope];
      }
      return current.filter((item) => item !== scope);
    });
  }

  async function copyKey(): Promise<void> {
    if (!created?.full_key) return;
    await navigator.clipboard.writeText(created.full_key);
    toast({ title: "คัดลอก API Key แล้ว" });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>สร้าง API Key</DialogTitle>
        </DialogHeader>

        {created ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
              <p className="font-semibold text-amber-900">คัดลอก API Key นี้ทันที</p>
              <p className="text-sm text-amber-800">จะไม่แสดงอีก</p>
              <div className="mt-4 flex flex-col gap-3 rounded-lg border border-amber-300 bg-white p-4 md:flex-row md:items-center md:justify-between">
                <code className="break-all text-sm font-semibold text-slate-900">{created.full_key}</code>
                <Button type="button" onClick={() => void copyKey()}>
                  <Copy className="h-4 w-4" />
                  Copy
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>ปิด</Button>
            </DialogFooter>
          </div>
        ) : (
          <>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>ชื่อ API Key*</Label>
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </div>
              <div className="space-y-3">
                <Label>Scopes</Label>
                {scopeOptions.map((scope) => (
                  <label key={scope.value} className="flex items-start gap-3 rounded-lg border p-3">
                    <Checkbox
                      checked={scopes.includes(scope.value)}
                      onCheckedChange={(checked) => toggleScope(scope.value, checked === true)}
                    />
                    <div>
                      <div className="font-mono text-sm">{scope.label}</div>
                      <div className="text-sm text-gray-500">{scope.description}</div>
                    </div>
                  </label>
                ))}
              </div>
              <div className="space-y-2">
                <Label>หมดอายุ</Label>
                <Input type="date" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
              <Button onClick={() => mutation.mutate()} disabled={mutation.isPending || !name.trim() || scopes.length === 0}>
                {mutation.isPending ? "กำลังสร้าง..." : "สร้าง API Key"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
