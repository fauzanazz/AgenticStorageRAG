"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  MessageSquare,
  Network,
  Upload,
  BarChart3,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";

interface DashboardStats {
  total_documents: number;
  total_chunks: number;
  total_entities: number;
  total_relationships: number;
  total_embeddings: number;
  processing_documents: number;
}

const STAT_CONFIG = [
  {
    key: "total_documents" as const,
    label: "Documents",
    icon: FileText,
    color: "#6366F1",
  },
  {
    key: "total_entities" as const,
    label: "Knowledge Nodes",
    icon: Network,
    color: "#A855F7",
  },
  {
    key: "total_chunks" as const,
    label: "Chunks",
    icon: MessageSquare,
    color: "#22D3EE",
  },
  {
    key: "total_embeddings" as const,
    label: "Embeddings",
    icon: BarChart3,
    color: "#EC4899",
  },
];

const QUICK_ACTIONS = [
  {
    title: "Upload Document",
    description: "Add PDF or DOCX files to your knowledge base",
    href: "/documents",
    icon: Upload,
    gradient: "linear-gradient(135deg, #6366F1, #818CF8)",
  },
  {
    title: "Start Chat",
    description: "Ask questions about your documents",
    href: "/chat",
    icon: MessageSquare,
    gradient: "linear-gradient(135deg, #A855F7, #C084FC)",
  },
  {
    title: "Knowledge Graph",
    description: "Visualize connections between concepts",
    href: "/knowledge",
    icon: Network,
    gradient: "linear-gradient(135deg, #22D3EE, #67E8F9)",
  },
  {
    title: "View Documents",
    description: "Manage your uploaded documents",
    href: "/documents",
    icon: FileText,
    gradient: "linear-gradient(135deg, #F59E0B, #FCD34D)",
  },
];

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<DashboardStats>("/documents/stats/dashboard")
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {
        // Non-critical -- dashboard works without stats
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-8">
      {/* Greeting */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">
          Welcome back{user?.full_name ? `, ${user.full_name}` : ""}
        </h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Your intelligent knowledge assistant is ready.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CONFIG.map((stat) => {
          const value = stats ? stats[stat.key] : null;
          return (
            <div
              key={stat.label}
              className="rounded-2xl p-5"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <div className="flex items-center justify-between mb-4">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{ background: `${stat.color}20` }}
                >
                  <stat.icon className="size-5" style={{ color: stat.color }} />
                </div>
              </div>
              <div className="text-3xl font-bold text-white mb-1">
                {value !== null ? formatNumber(value) : "--"}
              </div>
              <div className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
                {stat.label}
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_ACTIONS.map((action) => (
            <Link key={action.title} href={action.href}>
              <div
                className="rounded-2xl p-5 transition-all hover:scale-[1.02] cursor-pointer"
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: action.gradient }}
                >
                  <action.icon className="size-5 text-white" />
                </div>
                <div className="text-sm font-semibold text-white mb-1">
                  {action.title}
                </div>
                <div className="text-xs" style={{ color: "rgba(255,255,255,0.4)" }}>
                  {action.description}
                </div>
                <div className="flex items-center gap-1 mt-3 text-xs font-medium" style={{ color: "#818CF8" }}>
                  <Zap className="size-3" />
                  Get started
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
