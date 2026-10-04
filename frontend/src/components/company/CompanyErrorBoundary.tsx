import { Component, type ErrorInfo, type ReactNode } from "react";
import CompanyStatePanel from "@/components/company/CompanyStatePanel";

type Props = { children: ReactNode; resetKey: string };
type State = { failed: boolean };

export default class CompanyErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Company workspace render failed", error, info.componentStack);
  }

  componentDidUpdate(previous: Props): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render(): ReactNode {
    if (this.state.failed) {
      return (
        <CompanyStatePanel
          kind="error"
          title="ส่วนแสดงผลนี้มีปัญหา"
          description="ข้อมูลส่วนอื่นของระบบยังปลอดภัย กรุณาโหลดหน้าใหม่เพื่อเริ่มพื้นที่ทำงานอีกครั้ง"
          onRetry={() => window.location.reload()}
        />
      );
    }
    return this.props.children;
  }
}
