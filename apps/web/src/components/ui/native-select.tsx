import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function NativeSelect({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn("flex h-9 rounded-md border border-emerald-200 bg-white px-3 py-1 text-sm text-emerald-950 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 disabled:cursor-not-allowed disabled:opacity-50", className)} {...props} />;
}
