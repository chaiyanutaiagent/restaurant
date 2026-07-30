import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/components/ui/use-toast";
import { crmApi } from "@/lib/crmApi";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  requirePhone: boolean;
  onCreated?: (customerId: string) => void;
};

export default function CreateCustomerDialog({ open, onOpenChange, requirePhone, onCreated }: Props): JSX.Element {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    if (!open) {
      setFirstName("");
      setLastName("");
      setDisplayName("");
      setPhone("");
      setEmail("");
      setDateOfBirth("");
      setNote("");
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: async () => {
      if (requirePhone && !phone.trim()) throw new Error("กรุณากรอกเบอร์โทร");
      return crmApi.createCustomer({
        first_name: firstName || null,
        last_name: lastName || null,
        display_name: displayName || null,
        phone: phone || null,
        email: email || null,
        date_of_birth: dateOfBirth || null,
        note: note || null,
        tag_ids: []
      });
    },
    onSuccess: async (response) => {
      const customer = response.data.data as { id: string; customer_code: string };
      toast({ title: `เพิ่มสมาชิกแล้ว: ${customer.customer_code}` });
      onCreated?.(customer.id);
      onOpenChange(false);
      await queryClient.invalidateQueries({ queryKey: ["crm"] });
    },
    onError: (error: Error) => {
      toast({ title: "เพิ่มสมาชิกไม่สำเร็จ", description: error.message, variant: "destructive" });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>เพิ่มสมาชิก</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>ชื่อ</Label>
            <Input value={firstName} onChange={(event) => setFirstName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>นามสกุล</Label>
            <Input value={lastName} onChange={(event) => setLastName(event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>ชื่อแสดงผล</Label>
            <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>เบอร์โทร{requirePhone ? " *" : ""}</Label>
            <Input value={phone} onChange={(event) => setPhone(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>อีเมล</Label>
            <Input value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>วันเกิด</Label>
            <Input type="date" value={dateOfBirth} onChange={(event) => setDateOfBirth(event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>หมายเหตุ</Label>
            <textarea className="min-h-[100px] w-full rounded-md border border-gray-300 px-3 py-2" value={note} onChange={(event) => setNote(event.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>ยกเลิก</Button>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? "กำลังบันทึก..." : "บันทึก"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
