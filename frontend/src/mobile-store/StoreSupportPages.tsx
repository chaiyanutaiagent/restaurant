import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ApiResponse } from "@/types/api";
import type { TakeawayRecord } from "../lib/takeawayApi";
import api from "./api";

export function StoreCreditPage(): JSX.Element {
  const client = useQueryClient();
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const query = useQuery({ queryKey: ["store-credit"], queryFn: async () => (await api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/credit/accounts")).data.data });
  const history = useQuery({ queryKey: ["store-credit-topups"], queryFn: async () => (await api.get<ApiResponse<TakeawayRecord[]>>("/takeaway/credit/topups")).data.data });
  const request = useMutation({ mutationFn: (id: string) => api.post(`/takeaway/credit/accounts/${id}/topups`, {
    amount, payment_method: "bank_transfer", payment_reference: reference, idempotency_key: `store-topup:${requestKey}`,
  }), onSuccess: async () => { setAmount(""); setReference(""); setRequestKey(crypto.randomUUID()); await client.invalidateQueries({ queryKey: ["store-credit-topups"] }); } });
  return <section className="space-y-3 rounded-xl bg-white p-5"><h1 className="text-xl font-bold">เครดิตสาขา</h1><p>ผู้จัดการตรวจยอดและส่งคำขอชำระเครดิตให้ส่วนกลางตรวจสอบ</p>{query.isPending ? <p>กำลังโหลด…</p> : query.isError ? <p role="alert">โหลดเครดิตไม่สำเร็จ <button onClick={() => void query.refetch()}>ลองอีกครั้ง</button></p> : !query.data.length ? <p>ยังไม่มีบัญชีเครดิต</p> : query.data.map((row) => <div key={row.id} className="space-y-2 rounded border p-3"><p>วงเงิน {String(row.credit_limit)} · ยอดใช้ {String(row.balance)}</p><label className="block">ยอดชำระ<input aria-label="ยอดชำระเครดิต" type="number" min="0.01" step="0.01" className="ml-2 rounded border p-3" value={amount} onChange={(event) => setAmount(event.target.value)} /></label><label className="block">เลขอ้างอิงการโอน<input aria-label="เลขอ้างอิงการโอน" className="ml-2 rounded border p-3" value={reference} onChange={(event) => setReference(event.target.value)} /></label><button className="rounded bg-emerald-700 p-3 text-white" disabled={request.isPending || !(Number(amount) > 0) || !reference.trim()} onClick={() => request.mutate(row.id)}>ส่งให้ส่วนกลางตรวจสอบ</button></div>)}{request.isError && <p role="alert">ส่งไม่สำเร็จ ลองอีกครั้งด้วยรายการเดิม</p>}{request.isSuccess && <p role="status">ส่งคำขอแล้ว รอส่วนกลางตรวจสอบ</p>}<h2 className="font-bold">ประวัติคำขอ</h2>{history.data?.map((row) => <p key={row.id}>{String(row.amount)} · {String(row.status)}</p>)}</section>;
}

export function StoreTransfersPage(): JSX.Element {
  const client = useQueryClient();
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  type Transfer = TakeawayRecord & { items: Array<{ id: string; item_id: string; unit: string; shipped_qty: string }> };
  const query = useQuery({ queryKey: ["store-transfers"], queryFn: async () => (await api.get<ApiResponse<Transfer[]>>("/takeaway/store/transfers")).data.data });
  const receive = useMutation({ mutationFn: (row: Transfer) => api.post(`/takeaway/transfers/${row.id}/receive`, {
    lines: row.items.map((item) => ({ item_id: item.id, quantity: quantities[item.id] })), idempotency_key: `receive:${row.id}:${crypto.randomUUID()}`,
  }), onSuccess: () => client.invalidateQueries({ queryKey: ["store-transfers"] }) });
  return <section className="space-y-3 rounded-xl bg-white p-5"><h1 className="text-xl font-bold">รับโอนสินค้า</h1>{query.isPending ? <p>กำลังโหลด…</p> : query.isError ? <p role="alert">โหลดรายการไม่สำเร็จ</p> : !query.data.length ? <p>ไม่มีรายการโอน</p> : query.data.map((row) => <div className="space-y-2 rounded border p-3" key={row.id}><p>{String(row.transfer_number)} · {String(row.status)}</p>{row.status === "shipped" && <>{row.items.map((item) => <label key={item.id} className="block">{item.item_id} · ส่ง {item.shipped_qty} {item.unit}<input aria-label={`จำนวนรับ ${item.id}`} type="number" min="0" max={item.shipped_qty} step="0.0001" className="ml-2 rounded border p-3" value={quantities[item.id] ?? ""} onChange={(event) => setQuantities({ ...quantities, [item.id]: event.target.value })} /></label>)}<button className="rounded bg-emerald-700 p-3 text-white" disabled={receive.isPending || row.items.some((item) => quantities[item.id] === undefined || quantities[item.id] === "")} onClick={() => receive.mutate(row)}>ยืนยันยอดรับจริง</button></>}</div>)}{receive.isError && <p role="alert">รับสินค้าไม่สำเร็จ กรุณาตรวจจำนวนและสิทธิ์</p>}</section>;
}
