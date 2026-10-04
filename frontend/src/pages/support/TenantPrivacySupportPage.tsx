import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Headphones, Shield, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { privacySupportApi } from "@/lib/api";
import type { PrivacyRequest, SupportTicket } from "@/types/privacySupport";

export default function TenantPrivacySupportPage(): JSX.Element {
  const queryClient = useQueryClient();
  const privacy = useQuery({ queryKey: ["privacy-support", "privacy"], queryFn: async () => (await privacySupportApi.privacyRequests()).data.data });
  const tickets = useQuery({ queryKey: ["privacy-support", "tickets"], queryFn: async () => (await privacySupportApi.tickets()).data.data });
  const [requestType, setRequestType] = useState<PrivacyRequest["request_type"]>("access");
  const [privacyDescription, setPrivacyDescription] = useState("");
  const [ticketCategory, setTicketCategory] = useState<SupportTicket["category"]>("technical");
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");
  const [decisionReason, setDecisionReason] = useState("");

  const refresh = () => Promise.all([
    queryClient.invalidateQueries({ queryKey: ["privacy-support", "privacy"] }),
    queryClient.invalidateQueries({ queryKey: ["privacy-support", "tickets"] }),
  ]);
  const createPrivacy = useMutation({
    mutationFn: () => privacySupportApi.createPrivacyRequest({ request_type: requestType, description: privacyDescription.trim() || null }),
    onSuccess: () => { setPrivacyDescription(""); void refresh(); },
  });
  const createTicket = useMutation({
    mutationFn: () => {
      if (!ticketSubject.trim() || !ticketMessage.trim()) throw new Error("กรุณากรอกหัวข้อและรายละเอียด");
      return privacySupportApi.createTicket({ category: ticketCategory, priority: "normal", subject: ticketSubject, initial_message: ticketMessage });
    },
    onSuccess: () => { setTicketSubject(""); setTicketMessage(""); void refresh(); },
  });
  const decide = useMutation({
    mutationFn: ({ grantId, decision }: { grantId: string; decision: "approved" | "denied" }) => {
      if (!decisionReason.trim()) throw new Error("กรุณาระบุเหตุผลก่อนตัดสินใจ");
      return privacySupportApi.decideAccess(grantId, decision, decisionReason);
    },
    onSuccess: () => { setDecisionReason(""); void refresh(); },
  });

  const pendingGrants = tickets.data?.flatMap((ticket) => ticket.access_grants.filter((grant) => grant.status === "pending")) ?? [];
  const error = privacy.error ?? tickets.error ?? createPrivacy.error ?? createTicket.error ?? decide.error;
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div><h1 className="text-2xl font-bold text-gray-900">ความเป็นส่วนตัวและการช่วยเหลือ</h1><p className="mt-1 text-sm text-gray-500">สำหรับเจ้าของบัญชี SaaS นี้เท่านั้น คำขอไม่ลบข้อมูลอัตโนมัติ</p></div>
      {error ? <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error instanceof Error ? error.message : "ดำเนินการไม่สำเร็จ"}</p> : null}
      {pendingGrants.length ? <section className="rounded-xl border border-amber-300 bg-amber-50 p-5"><div className="flex items-center gap-2"><Shield className="h-5 w-5 text-amber-700" /><h2 className="font-semibold text-amber-950">คำขอสิทธิ์ช่วยเหลือรออนุมัติ</h2></div><div className="mt-4 space-y-4">{pendingGrants.map((grant) => <article key={grant.id} className="rounded-lg border border-amber-200 bg-white p-4"><p className="font-medium">{grant.purpose}</p><p className="mt-1 text-sm text-gray-600">ขอบเขต: {grant.requested_scopes.join(", ")} · {grant.duration_minutes} นาที</p><div className="mt-3 flex flex-wrap gap-2"><Input aria-label="เหตุผลการตัดสินใจ support access" value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} placeholder="เหตุผลการอนุมัติ/ปฏิเสธ" className="max-w-sm" /><Button onClick={() => decide.mutate({ grantId: grant.id, decision: "approved" })}><Check className="h-4 w-4" />อนุมัติ</Button><Button variant="outline" onClick={() => decide.mutate({ grantId: grant.id, decision: "denied" })}><X className="h-4 w-4" />ปฏิเสธ</Button></div></article>)}</div></section> : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center gap-2"><Shield className="h-5 w-5 text-blue-600" /><h2 className="text-lg font-semibold">คำขอด้านข้อมูลส่วนบุคคล</h2></div><div className="mt-4 space-y-3"><Label htmlFor="privacy-request-type">ประเภทคำขอ</Label><select id="privacy-request-type" className="h-10 w-full rounded-md border px-3" value={requestType} onChange={(event) => setRequestType(event.target.value as PrivacyRequest["request_type"])}>{["access", "export", "correction", "deletion", "restriction", "objection", "consent_withdrawal"].map((value) => <option key={value}>{value}</option>)}</select><Label htmlFor="privacy-request-description">รายละเอียด</Label><textarea id="privacy-request-description" className="min-h-24 w-full rounded-md border p-3 text-sm" value={privacyDescription} onChange={(event) => setPrivacyDescription(event.target.value)} /><Button onClick={() => createPrivacy.mutate()} disabled={createPrivacy.isPending}>ส่งคำขอ</Button></div><div className="mt-5 space-y-2">{privacy.data?.map((item) => <article key={item.id} className="rounded-lg border p-3 text-sm"><div className="flex justify-between"><span className="font-medium">{item.request_type}</span><span>{item.status}</span></div><p className="mt-1 text-gray-500">เป้าหมายภายใน {new Date(item.target_at).toLocaleDateString("th-TH")}</p></article>)}</div></section>
        <section className="rounded-xl border bg-white p-5 shadow-sm"><div className="flex items-center gap-2"><Headphones className="h-5 w-5 text-emerald-600" /><h2 className="text-lg font-semibold">Support ticket</h2></div><div className="mt-4 space-y-3"><Label htmlFor="support-category">หมวดหมู่</Label><select id="support-category" className="h-10 w-full rounded-md border px-3" value={ticketCategory} onChange={(event) => setTicketCategory(event.target.value as SupportTicket["category"])}>{["account", "billing", "technical", "privacy", "other"].map((value) => <option key={value}>{value}</option>)}</select><Label htmlFor="support-subject">หัวข้อ</Label><Input id="support-subject" value={ticketSubject} onChange={(event) => setTicketSubject(event.target.value)} /><Label htmlFor="support-message">รายละเอียด</Label><textarea id="support-message" className="min-h-24 w-full rounded-md border p-3 text-sm" value={ticketMessage} onChange={(event) => setTicketMessage(event.target.value)} /><Button onClick={() => createTicket.mutate()} disabled={createTicket.isPending}>เปิด Ticket</Button></div><div className="mt-5 space-y-2">{tickets.data?.map((ticket) => <article key={ticket.id} className="rounded-lg border p-3 text-sm"><div className="flex justify-between"><span className="font-medium">{ticket.ticket_number}</span><span>{ticket.status}</span></div><p className="mt-1">{ticket.subject}</p><p className="mt-1 text-gray-500">ข้อความ {ticket.messages.length} · access requests {ticket.access_grants.length}</p></article>)}</div></section>
      </div>
    </div>
  );
}
