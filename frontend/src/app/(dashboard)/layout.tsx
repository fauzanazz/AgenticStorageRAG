"use client";

import { redirect } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { AppTopNav } from "@/components/layout/app-top-nav";
import { PageLoader } from "@/components/ui/page-loader";
import { Toaster } from "@/components/ui/sonner";

/**
 * Dashboard layout -- requires authentication.
 * Top navigation bar + full-width main content area.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isAuthenticated) {
    redirect("/login");
  }

  return (
    <div className="flex flex-col h-dvh overflow-hidden" style={{ background: "var(--background)" }}>
      <AppTopNav />
      <main className="flex-1 min-w-0 flex flex-col overflow-y-auto">
        {children}
      </main>
      <Toaster />
    </div>
  );
}
