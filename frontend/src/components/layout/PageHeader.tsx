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
    <div className="mb-5 flex flex-col gap-3 border-b border-slate-200 pb-4 md:mb-6 md:flex-row md:items-end md:justify-between md:pb-5">
      <div className="min-w-0">
        <h1 className="truncate text-2xl font-black tracking-tight text-slate-950 md:text-[1.75rem]">{title}</h1>
        {subtitle ? <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2 md:justify-end">{actions}</div> : null}
    </div>
  );
}
