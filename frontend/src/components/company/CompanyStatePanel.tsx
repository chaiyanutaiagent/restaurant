import { SystemState, type SystemStateKind } from "@/components/ui/system-state";

export type CompanyStateKind = SystemStateKind;

type CompanyStatePanelProps = {
  kind: CompanyStateKind;
  title?: string;
  description?: string;
  compact?: boolean;
  onRetry?: () => void;
};

export default function CompanyStatePanel({
  kind,
  title,
  description,
  compact = false,
  onRetry,
}: CompanyStatePanelProps): JSX.Element {
  return <SystemState kind={kind} title={title} description={description} compact={compact} onAction={onRetry} />;
}
