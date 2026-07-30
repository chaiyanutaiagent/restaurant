import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronDown, ChevronRight, Lock, Plus, RefreshCcw } from "lucide-react";
import { useMemo, useState } from "react";
import PageHeader from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import { accountingApi } from "@/lib/accountingApi";
import { cn, formatDateTimeTh } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth.store";
import type { Account, JournalEntry, JournalLine, ProfitLossReport, TrialBalanceReport } from "@/types/accounting";

const thaiMonths = [
  "",
  "มกราคม",
  "กุมภาพันธ์",
  "มีนาคม",
  "เมษายน",
  "พฤษภาคม",
  "มิถุนายน",
  "กรกฎาคม",
  "สิงหาคม",
  "กันยายน",
  "ตุลาคม",
  "พฤศจิกายน",
  "ธันวาคม"
];

const currentDate = new Date();
const defaultThaiYear = currentDate.getFullYear() + 543;
const defaultMonth = currentDate.getMonth() + 1;

type EntryLineForm = {
  account_id: string;
  description: string;
  debit_amount: string;
  credit_amount: string;
};

type AccountFormState = {
  parent_id: string;
  code: string;
  name: string;
  name_en: string;
  account_type: string;
  account_subtype: string;
  normal_balance: "debit" | "credit";
  is_header: boolean;
  description: string;
};

const defaultAccountForm: AccountFormState = {
  parent_id: "",
  code: "",
  name: "",
  name_en: "",
  account_type: "asset",
  account_subtype: "current_asset",
  normal_balance: "debit",
  is_header: false,
  description: ""
};

const defaultManualLines = (): EntryLineForm[] => [
  { account_id: "", description: "", debit_amount: "", credit_amount: "" },
  { account_id: "", description: "", debit_amount: "", credit_amount: "" }
];

function formatCurrency(value: number | string): string {
  const amount = typeof value === "number" ? value : Number(value || 0);
  return new Intl.NumberFormat("th-TH", {
    style: "currency",
    currency: "THB",
    minimumFractionDigits: 2
  }).format(amount || 0);
}

function formatThaiDate(value: string): string {
  const date = new Date(value);
  return `${date.getDate()} ${thaiMonths[date.getMonth() + 1]} ${date.getFullYear() + 543}`;
}

function accountTypeBadge(accountType: string): string {
  switch (accountType) {
    case "asset":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "liability":
      return "border-red-200 bg-red-50 text-red-700";
    case "equity":
      return "border-violet-200 bg-violet-50 text-violet-700";
    case "revenue":
      return "border-green-200 bg-green-50 text-green-700";
    default:
      return "border-orange-200 bg-orange-50 text-orange-700";
  }
}

function entryTypeBadge(entryType: string): "default" | "secondary" | "success" | "outline" {
  switch (entryType) {
    case "sale":
      return "success";
    case "purchase":
      return "default";
    case "adjustment":
      return "secondary";
    default:
      return "outline";
  }
}

function entryTypeLabel(entryType: string): string {
  switch (entryType) {
    case "sale":
      return "ขาย";
    case "purchase":
      return "ซื้อ";
    case "adjustment":
      return "ปรับปรุง";
    case "manual":
      return "บันทึกทั่วไป";
    default:
      return entryType;
  }
}

function subtypeOptions(accountType: string): Array<{ value: string; label: string }> {
  switch (accountType) {
    case "asset":
      return [
        { value: "current_asset", label: "สินทรัพย์หมุนเวียน" },
        { value: "fixed_asset", label: "สินทรัพย์ถาวร" },
        { value: "other_asset", label: "สินทรัพย์อื่น" }
      ];
    case "liability":
      return [
        { value: "current_liability", label: "หนี้สินหมุนเวียน" },
        { value: "long_term_liability", label: "หนี้สินระยะยาว" }
      ];
    case "equity":
      return [
        { value: "capital", label: "ทุน" },
        { value: "retained_earnings", label: "กำไรสะสม" }
      ];
    case "revenue":
      return [
        { value: "sales", label: "รายได้จากการขาย" },
        { value: "other_revenue", label: "รายได้อื่น" }
      ];
    default:
      return [
        { value: "cost_of_goods", label: "ต้นทุนขาย" },
        { value: "operating", label: "ค่าใช้จ่ายดำเนินงาน" },
        { value: "other_expense", label: "ค่าใช้จ่ายอื่น" }
      ];
  }
}

type AccountNodeProps = {
  account: Account;
  level?: number;
  onCreateChild: (account: Account) => void;
};

function AccountNode({ account, level = 0, onCreateChild }: AccountNodeProps): JSX.Element {
  const [open, setOpen] = useState(true);
  const hasChildren = account.children.length > 0;

  return (
    <div className="space-y-2">
      <div
        className={cn(
          "flex items-center gap-3 rounded-lg border px-3 py-3",
          account.is_header ? "border-gray-200 bg-gray-50 font-semibold" : "border-gray-100 bg-white"
        )}
        style={{ marginLeft: `${level * 18}px` }}
      >
        <button
          type="button"
          className="flex h-6 w-6 items-center justify-center rounded text-gray-500"
          onClick={() => setOpen((value) => !value)}
        >
          {hasChildren ? (
            open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />
          ) : (
            <span className="h-4 w-4" />
          )}
        </button>
        <span className="w-16 font-mono text-sm text-gray-700">{account.code}</span>
        <span className="flex-1 text-sm text-gray-900">{account.name}</span>
        <Badge className={cn("border", accountTypeBadge(account.account_type))}>{account.account_type}</Badge>
        <span className="w-16 text-xs uppercase text-gray-500">{account.normal_balance}</span>
        <div className="flex items-center gap-2">
          {account.is_system ? <Lock className="h-4 w-4 text-gray-400" /> : null}
          <Button size="sm" variant="ghost" onClick={() => onCreateChild(account)} disabled={!account.is_header}>
            เพิ่มบัญชี
          </Button>
        </div>
      </div>
      {open && hasChildren ? (
        <div className="space-y-2">
          {account.children.map((child) => (
            <AccountNode key={child.id} account={child} level={level + 1} onCreateChild={onCreateChild} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function AccountingPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const hasPermission = useAuthStore((state) => state.hasPermission);

  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [entryDialogOpen, setEntryDialogOpen] = useState(false);
  const [entryDetailId, setEntryDetailId] = useState<string | null>(null);
  const [accountForm, setAccountForm] = useState<AccountFormState>(defaultAccountForm);
  const [entryDate, setEntryDate] = useState("2026-05-14");
  const [entryDescription, setEntryDescription] = useState("");
  const [entryLines, setEntryLines] = useState<EntryLineForm[]>(defaultManualLines);
  const [entryTypeFilter, setEntryTypeFilter] = useState("");
  const [entryAccountFilter, setEntryAccountFilter] = useState("");
  const [entryPeriodMonth, setEntryPeriodMonth] = useState(defaultMonth);
  const [entryPeriodYear, setEntryPeriodYear] = useState(defaultThaiYear);
  const [trialMonth, setTrialMonth] = useState(defaultMonth);
  const [trialYear, setTrialYear] = useState(defaultThaiYear);
  const [profitMonth, setProfitMonth] = useState(defaultMonth);
  const [profitYear, setProfitYear] = useState(defaultThaiYear);
  const [profitCumulative, setProfitCumulative] = useState(false);

  const treeAccountsQuery = useQuery({
    queryKey: ["accounting", "accounts", "tree"],
    queryFn: async () => (await accountingApi.listAccounts({ tree: true })).data.data
  });
  const flatAccountsQuery = useQuery({
    queryKey: ["accounting", "accounts", "flat"],
    queryFn: async () => (await accountingApi.listAccounts({ tree: false })).data.data
  });
  const entriesQuery = useQuery({
    queryKey: ["accounting", "entries", entryPeriodYear, entryPeriodMonth, entryTypeFilter, entryAccountFilter],
    queryFn: async () =>
      (
        await accountingApi.listEntries({
          period_year: entryPeriodYear,
          period_month: entryPeriodMonth,
          entry_type: entryTypeFilter || undefined,
          account_id: entryAccountFilter || undefined,
          page: 1,
          limit: 50
        })
      ).data
  });
  const entryDetailQuery = useQuery({
    queryKey: ["accounting", "entry", entryDetailId],
    enabled: Boolean(entryDetailId),
    queryFn: async () => (await accountingApi.getEntry(entryDetailId ?? "")).data.data
  });
  const trialBalanceQuery = useQuery({
    queryKey: ["accounting", "trial-balance", trialYear, trialMonth],
    queryFn: async () => (await accountingApi.trialBalance(trialYear, trialMonth)).data.data
  });
  const profitLossQuery = useQuery({
    queryKey: ["accounting", "profit-loss", profitYear, profitMonth, profitCumulative],
    queryFn: async () => (await accountingApi.profitLoss(profitYear, profitMonth, profitCumulative)).data.data
  });

  const headerAccounts = useMemo(
    () => (flatAccountsQuery.data ?? []).filter((account) => account.is_header),
    [flatAccountsQuery.data]
  );

  const manualAccounts = useMemo(
    () => (flatAccountsQuery.data ?? []).filter((account) => !account.is_header && account.is_active),
    [flatAccountsQuery.data]
  );

  const lineTotals = useMemo(() => {
    const debit = entryLines.reduce((sum, line) => sum + Number(line.debit_amount || 0), 0);
    const credit = entryLines.reduce((sum, line) => sum + Number(line.credit_amount || 0), 0);
    return { debit, credit, diff: debit - credit };
  }, [entryLines]);

  const createAccountMutation = useMutation({
    mutationFn: (payload: object) => accountingApi.createAccount(payload),
    onSuccess: async () => {
      setAccountDialogOpen(false);
      setAccountForm(defaultAccountForm);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounting", "accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "accounts", "tree"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "accounts", "flat"] })
      ]);
      toast({ title: "บันทึกสำเร็จ", description: "เพิ่มบัญชีใหม่เรียบร้อยแล้ว" });
    },
    onError: () => {
      toast({ title: "บันทึกไม่สำเร็จ", description: "ไม่สามารถเพิ่มบัญชีได้", variant: "destructive" });
    }
  });

  const createEntryMutation = useMutation({
    mutationFn: (payload: object) => accountingApi.createEntry(payload),
    onSuccess: async () => {
      setEntryDialogOpen(false);
      setEntryLines(defaultManualLines);
      setEntryDescription("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounting", "entries"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "trial-balance"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "profit-loss"] })
      ]);
      toast({ title: "บันทึกสำเร็จ", description: "สร้างรายการบัญชีแล้ว" });
    },
    onError: () => {
      toast({ title: "บันทึกไม่สำเร็จ", description: "กรุณาตรวจสอบความสมดุลของเดบิตและเครดิต", variant: "destructive" });
    }
  });

  const reverseEntryMutation = useMutation({
    mutationFn: (entryId: string) => accountingApi.reverseEntry(entryId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["accounting", "entries"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "trial-balance"] }),
        queryClient.invalidateQueries({ queryKey: ["accounting", "profit-loss"] })
      ]);
      toast({ title: "กลับรายการสำเร็จ", description: "สร้างรายการกลับรายการแล้ว" });
    },
    onError: () => {
      toast({ title: "กลับรายการไม่สำเร็จ", description: "ไม่สามารถกลับรายการได้", variant: "destructive" });
    }
  });

  function openCreateChild(parent?: Account): void {
    if (parent) {
      setAccountForm({
        ...defaultAccountForm,
        parent_id: parent.id,
        account_type: parent.account_type,
        account_subtype: parent.account_subtype ?? subtypeOptions(parent.account_type)[0]?.value ?? "",
        normal_balance: parent.account_type === "asset" || parent.account_type === "expense" ? "debit" : "credit"
      });
    } else {
      setAccountForm(defaultAccountForm);
    }
    setAccountDialogOpen(true);
  }

  function updateEntryLine(index: number, field: keyof EntryLineForm, value: string): void {
    setEntryLines((current) =>
      current.map((line, lineIndex) => (lineIndex === index ? { ...line, [field]: value } : line))
    );
  }

  function submitAccount(): void {
    createAccountMutation.mutate({
      parent_id: accountForm.parent_id || null,
      code: accountForm.code,
      name: accountForm.name,
      name_en: accountForm.name_en || null,
      account_type: accountForm.account_type,
      account_subtype: accountForm.account_subtype || null,
      normal_balance: accountForm.normal_balance,
      is_header: accountForm.is_header,
      is_active: true,
      description: accountForm.description || null,
      sort_order: Number(accountForm.code || 0)
    });
  }

  function submitManualEntry(): void {
    createEntryMutation.mutate({
      entry_date: entryDate,
      description: entryDescription,
      lines: entryLines.map((line) => ({
        account_id: line.account_id,
        description: line.description || null,
        debit_amount: Number(line.debit_amount || 0),
        credit_amount: Number(line.credit_amount || 0)
      }))
    });
  }

  const selectedParent = headerAccounts.find((account) => account.id === accountForm.parent_id);
  const currentSubtypeOptions = subtypeOptions(selectedParent?.account_type ?? accountForm.account_type);

  return (
    <div className="space-y-6">
      <PageHeader title="บัญชี" subtitle="ระบบบัญชีและรายงานทางการเงิน" />

      <Tabs defaultValue="accounts">
        <TabsList className="grid w-full grid-cols-2 gap-1 md:grid-cols-4">
          <TabsTrigger value="accounts">ผังบัญชี</TabsTrigger>
          <TabsTrigger value="journal">รายการบัญชี</TabsTrigger>
          <TabsTrigger value="trial-balance">งบทดลอง</TabsTrigger>
          <TabsTrigger value="profit-loss">กำไร-ขาดทุน</TabsTrigger>
        </TabsList>

        <TabsContent value="accounts">
          <Card>
            <CardHeader className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle>ผังบัญชี</CardTitle>
                <p className="text-sm text-gray-500">แสดงผังบัญชีแบบต้นไม้พร้อมสีตามประเภทบัญชี</p>
              </div>
              {hasPermission("accounting.invoice.create") ? (
                <Button onClick={() => openCreateChild()}>
                  <Plus className="mr-2 h-4 w-4" />
                  เพิ่มบัญชี
                </Button>
              ) : null}
            </CardHeader>
            <CardContent className="space-y-3">
              {(treeAccountsQuery.data ?? []).map((account) => (
                <AccountNode key={account.id} account={account} onCreateChild={openCreateChild} />
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="journal">
          <Card>
            <CardHeader className="flex flex-col gap-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div>
                  <CardTitle>รายการบัญชี</CardTitle>
                  <p className="text-sm text-gray-500">ติดตามรายการบัญชี, auto-post และบันทึกรายการทั่วไป</p>
                </div>
                {hasPermission("accounting.invoice.create") ? (
                  <Button onClick={() => setEntryDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    บันทึกรายการทั่วไป
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-3 md:grid-cols-4">
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={entryPeriodMonth}
                  onChange={(event) => setEntryPeriodMonth(Number(event.target.value))}
                >
                  {thaiMonths.slice(1).map((month, index) => (
                    <option key={month} value={index + 1}>
                      {month}
                    </option>
                  ))}
                </select>
                <Input
                  type="number"
                  value={entryPeriodYear}
                  onChange={(event) => setEntryPeriodYear(Number(event.target.value))}
                />
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={entryTypeFilter}
                  onChange={(event) => setEntryTypeFilter(event.target.value)}
                >
                  <option value="">ทั้งหมด</option>
                  <option value="sale">ขาย</option>
                  <option value="purchase">ซื้อ</option>
                  <option value="adjustment">ปรับปรุง</option>
                  <option value="manual">บันทึกทั่วไป</option>
                </select>
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={entryAccountFilter}
                  onChange={(event) => setEntryAccountFilter(event.target.value)}
                >
                  <option value="">ทุกบัญชี</option>
                  {manualAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.code} {account.name}
                    </option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>เลขที่</TableHead>
                    <TableHead>วันที่</TableHead>
                    <TableHead>ประเภท</TableHead>
                    <TableHead>คำอธิบาย</TableHead>
                    <TableHead className="text-right">ยอดเดบิต</TableHead>
                    <TableHead>อ้างอิง</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(entriesQuery.data?.data ?? []).map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="font-mono">{entry.entry_number}</TableCell>
                      <TableCell>{formatThaiDate(entry.entry_date)}</TableCell>
                      <TableCell>
                        <Badge variant={entryTypeBadge(entry.entry_type)}>{entryTypeLabel(entry.entry_type)}</Badge>
                      </TableCell>
                      <TableCell>{entry.description}</TableCell>
                      <TableCell className="text-right">{formatCurrency(entry.total_debit)}</TableCell>
                      <TableCell>{entry.reference_type ?? "-"}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="ghost" onClick={() => setEntryDetailId(entry.id)}>
                            ดูรายละเอียด
                          </Button>
                          {entry.entry_type === "manual" ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => reverseEntryMutation.mutate(entry.id)}
                              disabled={entry.is_reversed || reverseEntryMutation.isPending}
                            >
                              กลับรายการ
                            </Button>
                          ) : null}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="trial-balance">
          <Card>
            <CardHeader className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <CardTitle>งบทดลอง</CardTitle>
                <p className="text-sm text-gray-500">ตรวจสอบยอดเดบิตและเครดิตของบัญชีปลายงวด</p>
              </div>
              <div className="flex flex-col gap-2 md:flex-row">
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={trialMonth}
                  onChange={(event) => setTrialMonth(Number(event.target.value))}
                >
                  {thaiMonths.slice(1).map((month, index) => (
                    <option key={month} value={index + 1}>
                      {month}
                    </option>
                  ))}
                </select>
                <Input type="number" value={trialYear} onChange={(event) => setTrialYear(Number(event.target.value))} />
                <Button onClick={() => void trialBalanceQuery.refetch()}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  สร้างรายงาน
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-500">{trialBalanceQuery.data?.period_label}</p>
                <Badge variant={trialBalanceQuery.data?.is_balanced ? "success" : "destructive"}>
                  {trialBalanceQuery.data?.is_balanced ? "ยอดลงตัว" : "ยอดไม่ลงตัว"}
                </Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>รหัส</TableHead>
                    <TableHead>ชื่อบัญชี</TableHead>
                    <TableHead>ประเภท</TableHead>
                    <TableHead className="text-right">เดบิต</TableHead>
                    <TableHead className="text-right">เครดิต</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(trialBalanceQuery.data?.rows ?? []).map((row) => (
                    <TableRow key={row.account_code}>
                      <TableCell className="font-mono">{row.account_code}</TableCell>
                      <TableCell>{row.account_name}</TableCell>
                      <TableCell>{row.account_type}</TableCell>
                      <TableCell className="text-right">{formatCurrency(row.debit_balance)}</TableCell>
                      <TableCell className="text-right">{formatCurrency(row.credit_balance)}</TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="bg-gray-50 font-semibold">
                    <TableCell colSpan={3}>สรุปรวม</TableCell>
                    <TableCell className="text-right">{formatCurrency(trialBalanceQuery.data?.total_debit ?? 0)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(trialBalanceQuery.data?.total_credit ?? 0)}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="profit-loss">
          <Card>
            <CardHeader className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <CardTitle>กำไร-ขาดทุน</CardTitle>
                <p className="text-sm text-gray-500">สรุปรายได้ ต้นทุน และค่าใช้จ่ายของงวด</p>
              </div>
              <div className="flex flex-col gap-2 md:flex-row md:items-center">
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={profitMonth}
                  onChange={(event) => setProfitMonth(Number(event.target.value))}
                >
                  {thaiMonths.slice(1).map((month, index) => (
                    <option key={month} value={index + 1}>
                      {month}
                    </option>
                  ))}
                </select>
                <Input type="number" value={profitYear} onChange={(event) => setProfitYear(Number(event.target.value))} />
                <label className="flex items-center gap-2 text-sm text-gray-600">
                  <input
                    type="checkbox"
                    checked={profitCumulative}
                    onChange={(event) => setProfitCumulative(event.target.checked)}
                  />
                  สะสมตั้งแต่ต้นปี
                </label>
                <Button onClick={() => void profitLossQuery.refetch()}>
                  <RefreshCcw className="mr-2 h-4 w-4" />
                  สร้างรายงาน
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 rounded-xl bg-gray-50 p-5">
                <SummaryRow label="รายได้จากการขาย" value={profitLossQuery.data?.total_revenue ?? 0} />
                <SummaryRow label="(-) ต้นทุนขาย" value={profitLossQuery.data?.total_cogs ?? 0} />
                <SummaryRow
                  label="กำไรขั้นต้น"
                  value={profitLossQuery.data?.gross_profit ?? 0}
                  highlight={`${profitLossQuery.data?.gross_margin_pct ?? 0}%`}
                />
                <SummaryRow
                  label="(-) ค่าใช้จ่ายดำเนินงาน"
                  value={profitLossQuery.data?.total_operating_expense ?? 0}
                />
                <SummaryRow
                  label="กำไร(ขาดทุน) สุทธิ"
                  value={profitLossQuery.data?.net_profit ?? 0}
                  highlight={`${profitLossQuery.data?.net_margin_pct ?? 0}%`}
                  emphasized
                />
              </div>
              <details className="rounded-xl border border-gray-200 p-4" open>
                <summary className="cursor-pointer font-medium text-gray-900">รายได้รายละเอียด</summary>
                <ReportDetailRows rows={profitLossQuery.data?.revenue_rows ?? []} />
              </details>
              <details className="rounded-xl border border-gray-200 p-4">
                <summary className="cursor-pointer font-medium text-gray-900">ต้นทุนรายละเอียด</summary>
                <ReportDetailRows rows={profitLossQuery.data?.cogs_rows ?? []} />
              </details>
              <details className="rounded-xl border border-gray-200 p-4">
                <summary className="cursor-pointer font-medium text-gray-900">ค่าใช้จ่ายรายละเอียด</summary>
                <ReportDetailRows rows={profitLossQuery.data?.expense_rows ?? []} />
              </details>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={accountDialogOpen} onOpenChange={setAccountDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>เพิ่มบัญชี</DialogTitle>
            <DialogDescription>สร้างบัญชีใหม่ภายใต้ผังบัญชีปัจจุบัน</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm">
              <span>บัญชีแม่</span>
              <select
                className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                value={accountForm.parent_id}
                onChange={(event) => setAccountForm((current) => ({ ...current, parent_id: event.target.value }))}
              >
                <option value="">ไม่มี</option>
                {headerAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.code} {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span>รหัสบัญชี</span>
              <Input value={accountForm.code} onChange={(event) => setAccountForm((current) => ({ ...current, code: event.target.value }))} />
            </label>
            <label className="space-y-2 text-sm">
              <span>ชื่อบัญชี</span>
              <Input value={accountForm.name} onChange={(event) => setAccountForm((current) => ({ ...current, name: event.target.value }))} />
            </label>
            <label className="space-y-2 text-sm">
              <span>ชื่ออังกฤษ</span>
              <Input value={accountForm.name_en} onChange={(event) => setAccountForm((current) => ({ ...current, name_en: event.target.value }))} />
            </label>
            <label className="space-y-2 text-sm">
              <span>ประเภทบัญชี</span>
              <select
                className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                disabled={Boolean(selectedParent)}
                value={selectedParent?.account_type ?? accountForm.account_type}
                onChange={(event) =>
                  setAccountForm((current) => ({
                    ...current,
                    account_type: event.target.value,
                    normal_balance: event.target.value === "asset" || event.target.value === "expense" ? "debit" : "credit",
                    account_subtype: subtypeOptions(event.target.value)[0]?.value ?? ""
                  }))
                }
              >
                <option value="asset">asset</option>
                <option value="liability">liability</option>
                <option value="equity">equity</option>
                <option value="revenue">revenue</option>
                <option value="expense">expense</option>
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span>ประเภทย่อย</span>
              <select
                className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                value={accountForm.account_subtype}
                onChange={(event) => setAccountForm((current) => ({ ...current, account_subtype: event.target.value }))}
              >
                {currentSubtypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-2 text-sm">
              <span>ยอดปกติ</span>
              <select
                className="h-10 w-full rounded-md border border-gray-300 px-3 text-sm"
                value={accountForm.normal_balance}
                onChange={(event) =>
                  setAccountForm((current) => ({ ...current, normal_balance: event.target.value as "debit" | "credit" }))
                }
              >
                <option value="debit">debit</option>
                <option value="credit">credit</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={accountForm.is_header}
                onChange={(event) => setAccountForm((current) => ({ ...current, is_header: event.target.checked }))}
              />
              <span>เป็นบัญชีหัวข้อ</span>
            </label>
            <label className="space-y-2 text-sm md:col-span-2">
              <span>คำอธิบาย</span>
              <textarea
                className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={accountForm.description}
                onChange={(event) => setAccountForm((current) => ({ ...current, description: event.target.value }))}
              />
            </label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAccountDialogOpen(false)}>
              ยกเลิก
            </Button>
            <Button onClick={submitAccount} disabled={createAccountMutation.isPending}>
              บันทึก
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={entryDialogOpen} onOpenChange={setEntryDialogOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>บันทึกรายการทั่วไป</DialogTitle>
            <DialogDescription>เดบิตและเครดิตต้องสมดุลกันก่อนบันทึก</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-2 text-sm">
              <span>วันที่บันทึก</span>
              <Input type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
            </label>
            <label className="space-y-2 text-sm">
              <span>คำอธิบาย</span>
              <Input value={entryDescription} onChange={(event) => setEntryDescription(event.target.value)} />
            </label>
          </div>
          <div className="space-y-3">
            {entryLines.map((line, index) => (
              <div key={`${index + 1}`} className="grid gap-3 rounded-lg border border-gray-200 p-3 md:grid-cols-[2fr_2fr_1fr_1fr_auto]">
                <select
                  className="h-10 rounded-md border border-gray-300 px-3 text-sm"
                  value={line.account_id}
                  onChange={(event) => updateEntryLine(index, "account_id", event.target.value)}
                >
                  <option value="">เลือกบัญชี</option>
                  {manualAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.code} {account.name}
                    </option>
                  ))}
                </select>
                <Input value={line.description} onChange={(event) => updateEntryLine(index, "description", event.target.value)} placeholder="คำอธิบาย" />
                <Input type="number" value={line.debit_amount} onChange={(event) => updateEntryLine(index, "debit_amount", event.target.value)} placeholder="เดบิต" />
                <Input type="number" value={line.credit_amount} onChange={(event) => updateEntryLine(index, "credit_amount", event.target.value)} placeholder="เครดิต" />
                <Button
                  variant="ghost"
                  onClick={() => setEntryLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}
                  disabled={entryLines.length <= 2}
                >
                  ลบ
                </Button>
              </div>
            ))}
            <Button variant="ghost" onClick={() => setEntryLines((current) => [...current, defaultManualLines()[0]])}>
              <Plus className="mr-2 h-4 w-4" />
              เพิ่มบรรทัด
            </Button>
          </div>
          <div className="rounded-lg bg-gray-50 px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>Debit total: {formatCurrency(lineTotals.debit)}</span>
              <span>Credit total: {formatCurrency(lineTotals.credit)}</span>
              <span className={lineTotals.diff === 0 ? "text-green-600" : "text-red-600"}>
                Difference: {formatCurrency(Math.abs(lineTotals.diff))}
              </span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEntryDialogOpen(false)}>
              ยกเลิก
            </Button>
            <Button
              onClick={submitManualEntry}
              disabled={lineTotals.diff !== 0 || lineTotals.debit <= 0 || createEntryMutation.isPending}
            >
              บันทึก
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(entryDetailId)} onOpenChange={(open) => (!open ? setEntryDetailId(null) : undefined)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>รายละเอียดรายการบัญชี</DialogTitle>
            <DialogDescription>{entryDetailQuery.data?.entry_number}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-gray-200 p-4">
              <p className="mb-3 text-sm font-semibold text-gray-900">เดบิต</p>
              <div className="space-y-2">
                {(entryDetailQuery.data?.lines ?? [])
                  .filter((line) => Number(line.debit_amount) > 0)
                  .map((line) => (
                    <TAccountLine key={line.id} line={line} amount={line.debit_amount} />
                  ))}
              </div>
            </div>
            <div className="rounded-lg border border-gray-200 p-4">
              <p className="mb-3 text-sm font-semibold text-gray-900">เครดิต</p>
              <div className="space-y-2">
                {(entryDetailQuery.data?.lines ?? [])
                  .filter((line) => Number(line.credit_amount) > 0)
                  .map((line) => (
                    <TAccountLine key={line.id} line={line} amount={line.credit_amount} />
                  ))}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">
            <span>รวมเดบิต = รวมเครดิต</span>
            <span>{formatCurrency(entryDetailQuery.data?.total_debit ?? 0)} ✓</span>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  highlight,
  emphasized = false
}: {
  label: string;
  value: number;
  highlight?: string;
  emphasized?: boolean;
}): JSX.Element {
  return (
    <div className={cn("flex items-center justify-between border-b border-dashed border-gray-200 pb-3 last:border-b-0", emphasized ? "text-base font-semibold" : "text-sm")}>
      <span>{label}</span>
      <span className={cn(value >= 0 ? "text-green-700" : "text-red-700", "text-right")}>
        {formatCurrency(value)} {highlight ? <span className="ml-2 text-xs text-gray-500">({highlight})</span> : null}
      </span>
    </div>
  );
}

function ReportDetailRows({ rows }: { rows: Array<{ account_code: string; account_name: string; debit_balance: number; credit_balance: number }> }): JSX.Element {
  return (
    <div className="mt-3 space-y-2">
      {rows.map((row) => (
        <div key={row.account_code} className="flex items-center justify-between text-sm text-gray-700">
          <span className="font-mono">{row.account_code}</span>
          <span className="flex-1 px-3">{row.account_name}</span>
          <span>{formatCurrency(row.debit_balance || row.credit_balance)}</span>
        </div>
      ))}
    </div>
  );
}

function TAccountLine({ line, amount }: { line: JournalLine; amount: number }): JSX.Element {
  return (
    <div className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 text-sm">
      <span>
        <span className="font-mono text-gray-500">{line.account_code}</span> {line.account_name}
      </span>
      <span>{formatCurrency(amount)}</span>
    </div>
  );
}
