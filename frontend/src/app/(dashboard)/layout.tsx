"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/hooks/use-auth";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { PageLoader } from "@/components/ui/page-loader";

/**
 * Dashboard layout -- requires authentication.
 * Shows sidebar + main content area.
 */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return <PageLoader />;
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-dvh overflow-hidden" style={{ background: "#0A0A0F" }}>
      <AppSidebar />
      {/*
       * h-full flex flex-col so flex children (pages) can use flex-1 to fill the exact
       * remaining height. overflow-y-auto lets non-chat pages scroll their own content.
       * pt-14 clears the fixed mobile header; md:pt-0 on desktop (sidebar does it).
       */}
      <main className="flex-1 min-w-0 h-full flex flex-col overflow-y-auto pt-14 md:pt-0">
        {children}
      </main>
    </div>
  );
}
