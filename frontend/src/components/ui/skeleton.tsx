import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }): JSX.Element {
  return <div className={cn("animate-pulse rounded-md bg-gray-200", className)} />;
}
