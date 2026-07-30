import { clsx, type ClassValue } from "clsx";
import { format } from "date-fns";
import { th } from "date-fns/locale";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDateTimeTh(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  return format(new Date(value), "dd MMM yyyy HH:mm", { locale: th });
}

export function getDisplayName(displayName: string | null, username: string): string {
  return displayName || username;
}
