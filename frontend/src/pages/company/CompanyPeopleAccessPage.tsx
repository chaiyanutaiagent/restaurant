import { ArrowRight, ShieldCheck, UserRoundCog, Users } from "lucide-react";
import { Link } from "react-router-dom";
import PageHeader from "@/components/layout/PageHeader";
import { useAuthStore } from "@/stores/auth.store";

export default function CompanyPeopleAccessPage(): JSX.Element {
  const hasPermission = useAuthStore((state) => state.hasPermission);
  const destinations = [
    {
      title: "พนักงาน",
      description: "ดูบัญชีผู้ใช้ สถานะ และขอบเขตสาขาที่ได้รับมอบหมาย",
      to: "/users",
      icon: Users,
      visible: hasPermission("system.user.view"),
    },
    {
      title: "บทบาทและสิทธิ์",
      description: "ตรวจ Role, Permission และขอบเขต Company/Brand/Branch/Station",
      to: "/roles",
      icon: ShieldCheck,
      visible: hasPermission("system.role.view"),
    },
  ].filter((item) => item.visible);

  return (
    <div data-testid="company-people-access-page">
      <PageHeader
        title="พนักงานและสิทธิ์"
        subtitle="ทางเข้ากลางสำหรับจัดการคน บทบาท และขอบเขตตามสิทธิ์ที่ Server อนุญาต"
      />
      <div className="grid gap-4 md:grid-cols-2">
        {destinations.map((item) => (
          <Link key={item.to} to={item.to} className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-md">
            <span className="inline-flex rounded-2xl bg-blue-50 p-3 text-blue-700"><item.icon className="h-6 w-6" /></span>
            <h2 className="mt-4 text-lg font-black text-slate-950">{item.title}</h2>
            <p className="mt-1 text-sm leading-6 text-slate-600">{item.description}</p>
            <span className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-blue-700">เปิดพื้นที่จัดการ <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span>
          </Link>
        ))}
        {destinations.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-8 text-center text-slate-600 md:col-span-2">
            <UserRoundCog className="mx-auto h-8 w-8" />
            <p className="mt-3 font-black">ไม่มีสิทธิ์จัดการพนักงานหรือบทบาท</p>
            <p className="mt-1 text-sm">ติดต่อ Company Owner เพื่อขอสิทธิ์ที่เหมาะสม</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
