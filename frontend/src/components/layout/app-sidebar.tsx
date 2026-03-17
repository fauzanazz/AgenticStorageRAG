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
} from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const NAV_ITEMS = [
  { title: "Dashboard", href: "/", icon: LayoutDashboard },
  { title: "Documents", href: "/documents", icon: FileText },
  { title: "Knowledge Graph", href: "/knowledge", icon: Network },
  { title: "Chat", href: "/chat", icon: MessageSquare },
] as const;

const SETTINGS_ITEMS = [
  { title: "Settings", href: "/settings", icon: Settings },
] as const;

const ADMIN_ITEMS = [
  { title: "Ingestion", href: "/admin/ingestion", icon: Database },
] as const;

function NavLink({
  item,
  isActive,
  onClick,
}: {
  item: { title: string; href: string; icon: React.ComponentType<{ className?: string }> };
  isActive: boolean;
  onClick?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onClick}
      className="flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all"
      style={{
        background: isActive ? "rgba(99,102,241,0.12)" : "transparent",
        color: isActive ? "#818CF8" : "rgba(255,255,255,0.5)",
      }}
    >
      <item.icon className="size-[18px]" />
      <span>{item.title}</span>
    </Link>
  );
}

function SidebarContent({
  pathname,
  user,
  logout,
  onNavClick,
}: {
  pathname: string;
  user: ReturnType<typeof useAuth>["user"];
  logout: () => void;
  onNavClick?: () => void;
}) {
  return (
    <>
      {/* Nav groups */}
      <div className="flex-1 space-y-6 overflow-y-auto">
        <div>
          <p
            className="px-4 mb-2 text-xs font-semibold uppercase tracking-wider"
            style={{ color: "rgba(255,255,255,0.3)" }}
          >
            Main
          </p>
          <nav className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                isActive={
                  item.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(item.href)
                }
                onClick={onNavClick}
              />
            ))}
          </nav>
        </div>

        <div>
          <p
            className="px-4 mb-2 text-xs font-semibold uppercase tracking-wider"
            style={{ color: "rgba(255,255,255,0.3)" }}
          >
            System
          </p>
          <nav className="space-y-1">
            {SETTINGS_ITEMS.map((item) => (
              <NavLink
                key={item.href}
                item={item}
                isActive={pathname.startsWith(item.href)}
                onClick={onNavClick}
              />
            ))}
          </nav>
        </div>

        {user?.is_admin && (
          <div>
            <p
              className="px-4 mb-2 text-xs font-semibold uppercase tracking-wider"
              style={{ color: "rgba(255,255,255,0.3)" }}
            >
              Admin
            </p>
            <nav className="space-y-1">
              {ADMIN_ITEMS.map((item) => (
                <NavLink
                  key={item.href}
                  item={item}
                  isActive={pathname.startsWith(item.href)}
                  onClick={onNavClick}
                />
              ))}
            </nav>
          </div>
        )}
      </div>

      {/* User footer */}
      <div
        className="mt-4 pt-4"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}
      >
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3 min-w-0">
            <div
              className="w-8 h-8 shrink-0 rounded-full flex items-center justify-center text-xs font-semibold text-white"
              style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
            >
              {user?.full_name?.charAt(0)?.toUpperCase() || "U"}
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">
                {user?.full_name || "User"}
              </p>
              <p className="truncate text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
                {user?.email || ""}
              </p>
            </div>
          </div>
          <button
            onClick={logout}
            className="shrink-0 rounded-lg p-1.5 transition-colors hover:bg-white/5"
            style={{ color: "rgba(255,255,255,0.4)" }}
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const logoMark = (
    <div
      className="w-9 h-9 rounded-xl flex items-center justify-center text-white font-bold text-sm shrink-0"
      style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
    >
      D
    </div>
  );

  return (
    <>
      {/* ── Desktop sidebar ─────────────────────────────────────────── */}
      <aside
        className="hidden md:flex flex-col w-64 shrink-0 h-dvh sticky top-0 p-4"
        style={{
          background: "rgba(255,255,255,0.02)",
          borderRight: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <Link href="/" className="flex items-center gap-3 px-2 mb-8">
          {logoMark}
          <span className="text-white text-lg font-semibold tracking-tight">
            DingDong RAG
          </span>
        </Link>

        <SidebarContent pathname={pathname} user={user} logout={logout} />
      </aside>

      {/* ── Mobile top header ────────────────────────────────────────── */}
      <header
        className="md:hidden fixed top-0 inset-x-0 z-50 flex items-center justify-between h-14 px-4"
        style={{
          background: "rgba(10,10,15,0.92)",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
        }}
      >
        <Link href="/" className="flex items-center gap-2.5">
          {logoMark}
          <span className="text-white font-semibold tracking-tight">DingDong RAG</span>
        </Link>
        <button
          onClick={() => setMobileOpen(true)}
          className="p-2 rounded-xl hover:bg-white/5 transition-colors"
          style={{ color: "rgba(255,255,255,0.6)" }}
          aria-label="Open navigation menu"
        >
          <Menu className="size-5" />
        </button>
      </header>

      {/* ── Mobile nav drawer ────────────────────────────────────────── */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-[60]" role="dialog" aria-modal="true">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setMobileOpen(false)}
          />

          {/* Drawer panel */}
          <aside
            className="absolute inset-y-0 left-0 flex flex-col w-72 p-4"
            style={{
              background: "#0A0A0F",
              borderRight: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            {/* Drawer header */}
            <div className="flex items-center justify-between px-2 mb-8">
              <Link
                href="/"
                className="flex items-center gap-3"
                onClick={() => setMobileOpen(false)}
              >
                {logoMark}
                <span className="text-white text-lg font-semibold tracking-tight">
                  DingDong RAG
                </span>
              </Link>
              <button
                onClick={() => setMobileOpen(false)}
                className="p-1.5 rounded-lg hover:bg-white/5 transition-colors"
                style={{ color: "rgba(255,255,255,0.4)" }}
                aria-label="Close navigation menu"
              >
                <X className="size-4" />
              </button>
            </div>

            <SidebarContent
              pathname={pathname}
              user={user}
              logout={logout}
              onNavClick={() => setMobileOpen(false)}
            />
          </aside>
        </div>
      )}
    </>
  );
}
