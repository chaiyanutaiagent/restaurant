import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
};

export default function PageHeader({
  title,
  subtitle,
  actions
}: PageHeaderProps): JSX.Element {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
        {subtitle ? <p className="text-sm text-gray-500">{subtitle}</p> : null}
      </div>
      {actions ? <div>{actions}</div> : null}
    </div>
  );
}
