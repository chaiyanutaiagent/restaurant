import { AlertTriangle, ArrowLeft } from "lucide-react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function NotFoundPage(): JSX.Element {
  const location = useLocation();
  const isForbidden = location.pathname === "/403";

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
      <div className="rounded-full bg-red-50 p-4 text-red-600">
        <AlertTriangle className="h-10 w-10" />
      </div>
      <h1 className="mt-6 text-3xl font-bold text-gray-900">
        {isForbidden ? "ไม่มีสิทธิ์เข้าถึงหน้านี้" : "ไม่พบหน้านี้"}
      </h1>
      <p className="mt-2 max-w-md text-sm text-gray-500">
        {isForbidden
          ? "บัญชีของคุณยังไม่มีสิทธิ์ที่จำเป็นสำหรับหน้านี้"
          : "เส้นทางที่คุณเรียกใช้อาจถูกย้ายหรือลบออกจากระบบแล้ว"}
      </p>
      <Button asChild className="mt-6">
        <Link to="/admin">
          <ArrowLeft className="mr-2 h-4 w-4" />
          กลับไปหน้า ERP Admin
        </Link>
      </Button>
    </div>
  );
}
