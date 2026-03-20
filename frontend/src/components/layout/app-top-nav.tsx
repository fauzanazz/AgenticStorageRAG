"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  LayoutDashboard,
  MessageSquare,
  Network,
  Settings,
  LogOut,
  Database,
  Menu,
  X,
  ChevronDown,
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const NAV_ITEMS = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard },
  { title: "Documents", href: "/documents", icon: FileText },
  { title: "Knowledge Graph", href: "/knowledge", icon: Network },
  { title: "Chat", href: "/chat", icon: MessageSquare },
] as const;

const ADMIN_ITEMS = [
  { title: "Ingestion", href: "/admin/ingestion", icon: Database },
] as const;

export function AppTopNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const allNavItems = [
    ...NAV_ITEMS,
    ...(user?.is_admin ? ADMIN_ITEMS : []),
  ];

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const logoMark = (
    <div
      className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm shrink-0"
      style={{ background: "var(--primary)" }}
    >
      D
    </div>
  );

  return (
    <>
      <header
        className="sticky top-0 z-50 flex items-center h-16 px-4 lg:px-6 shrink-0 backdrop-blur-sm"
        style={{
          background: "var(--glass-bg)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 shrink-0 mr-8">
          {logoMark}
          <span className="font-semibold tracking-tight hidden sm:inline" style={{ color: "var(--foreground)" }}>
            DingDong RAG
          </span>
        </Link>

        {/* Desktop nav links */}
        <nav className="hidden md:flex items-center gap-1 flex-1">
          {allNavItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: isActive(item.href) ? "var(--accent)" : "transparent",
                color: isActive(item.href) ? "var(--primary)" : "var(--muted-foreground)",
              }}
            >
              <item.icon className="size-4" />
              <span>{item.title}</span>
            </Link>
          ))}
        </nav>

        {/* Right section */}
        <div className="hidden md:flex items-center gap-2 ml-auto">
          {/* Settings */}
          <Link
            href="/settings"
            className="p-2 rounded-lg transition-colors hover:bg-black/5"
            style={{
              color: isActive("/settings") ? "var(--primary)" : "var(--muted-foreground)",
            }}
            title="Settings"
          >
            <Settings className="size-[18px]" />
          </Link>

          {/* User menu */}
          <DropdownMenu>
            <DropdownMenuTrigger
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-black/5 outline-none"
            >
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0"
                style={{ background: "var(--primary)" }}
              >
                {user?.full_name?.charAt(0)?.toUpperCase() || "U"}
              </div>
              <span className="text-sm font-medium max-w-[120px] truncate hidden lg:inline" style={{ color: "var(--foreground)" }}>
                {user?.full_name || "User"}
              </span>
              <ChevronDown className="size-3.5" style={{ color: "var(--muted-foreground)" }} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={8} className="w-56">
              <div className="px-3 py-2">
                <p className="text-sm font-medium truncate">
                  {user?.full_name || "User"}
                </p>
                <p className="text-xs truncate text-muted-foreground">
                  {user?.email || ""}
                </p>
              </div>
              <DropdownMenuSeparator />
              <DropdownMenuItem render={<Link href="/settings" />}>
                <Settings className="size-4" />
                Settings
              </DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onClick={logout}>
                <LogOut className="size-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(true)}
          className="md:hidden ml-auto p-2 rounded-lg hover:bg-black/5 transition-colors"
          style={{ color: "var(--muted-foreground)" }}
          aria-label="Open navigation menu"
        >
          <Menu className="size-5" />
        </button>
      </header>

      {/* Mobile nav overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-[60]" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/40"
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " " || e.key === "Escape") { e.preventDefault(); setMobileOpen(false); } }}
            onClick={() => setMobileOpen(false)}
          />
          <div
            className="absolute inset-y-0 right-0 flex flex-col w-72 p-4"
            style={{
              background: "var(--background)",
              borderLeft: "1px solid var(--border)",
            }}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <span className="text-sm font-semibold" style={{ color: "var(--foreground)" }}>Menu</span>
              <button
                onClick={() => setMobileOpen(false)}
                className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
                style={{ color: "var(--muted-foreground)" }}
                aria-label="Close menu"
              >
                <X className="size-4" />
              </button>
            </div>

            {/* Nav links */}
            <nav className="flex-1 space-y-1">
              {allNavItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
                  style={{
                    background: isActive(item.href) ? "var(--accent)" : "transparent",
                    color: isActive(item.href) ? "var(--primary)" : "var(--muted-foreground)",
                  }}
                >
                  <item.icon className="size-[18px]" />
                  <span>{item.title}</span>
                </Link>
              ))}
              <Link
                href="/settings"
                onClick={() => setMobileOpen(false)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all"
                style={{
                  background: isActive("/settings") ? "var(--accent)" : "transparent",
                  color: isActive("/settings") ? "var(--primary)" : "var(--muted-foreground)",
                }}
              >
                <Settings className="size-[18px]" />
                <span>Settings</span>
              </Link>
            </nav>

            {/* User footer */}
            <div style={{ borderTop: "1px solid var(--border)" }} className="pt-4 mt-4">
              <div className="flex items-center gap-3 px-2 mb-3">
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0"
                  style={{ background: "var(--primary)" }}
                >
                  {user?.full_name?.charAt(0)?.toUpperCase() || "U"}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium" style={{ color: "var(--foreground)" }}>
                    {user?.full_name || "User"}
                  </p>
                  <p className="truncate text-xs" style={{ color: "var(--muted-foreground)" }}>
                    {user?.email || ""}
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  logout();
                }}
                className="flex w-full items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors hover:bg-black/5"
                style={{ color: "var(--destructive)" }}
              >
                <LogOut className="size-4" />
                Sign out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
