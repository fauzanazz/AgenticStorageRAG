"use client";

import { AuthProvider } from "@/hooks/use-auth";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

/**
 * Client-side providers wrapper.
 * Add any providers (auth, theme, toast, etc.) here.
 */
export function Providers({ children }: { children: ReactNode }) {
  // Create a stable QueryClient per session (not a module-level singleton so
  // that SSR/test environments each get a fresh instance).
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Data is considered fresh for 30 seconds; no background re-fetch on focus.
            staleTime: 30_000,
            // Keep unused cache entries for 5 minutes.
            gcTime: 5 * 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
      {process.env.NODE_ENV === "development" && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}
