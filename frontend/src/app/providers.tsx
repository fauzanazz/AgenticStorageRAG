"use client";

import { AuthProvider } from "@/hooks/use-auth";
import type { ReactNode } from "react";

/**
 * Client-side providers wrapper.
 * Add any providers (auth, theme, toast, etc.) here.
 */
export function Providers({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
