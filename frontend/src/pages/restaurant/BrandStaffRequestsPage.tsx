import { UsersRound } from "lucide-react";
import { useParams } from "react-router-dom";
import UserAccessRequestsPanel from "@/pages/users/UserAccessRequestsPanel";

export default function BrandStaffRequestsPage(): JSX.Element {
  const { brandSlug = "" } = useParams<{ brandSlug?: string }>();

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      <div>
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{brandSlug}</p>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-950">
          <UsersRound className="h-6 w-6" /> คำขอพนักงานของแบรนด์
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          ตรวจสอบคำขอจากสาขาที่เปิดใช้งานแบรนด์นี้เท่านั้น
        </p>
      </div>
      <UserAccessRequestsPanel brandSlug={brandSlug} />
    </div>
  );
}
