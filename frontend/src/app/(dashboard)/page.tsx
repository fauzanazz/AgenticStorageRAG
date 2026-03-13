"use client";

import { FileText, MessageSquare, Network, Upload } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { MobileHeader } from "@/components/layout/mobile-header";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const QUICK_ACTIONS = [
  {
    title: "Upload Document",
    description: "Add PDF or DOCX files to your knowledge base",
    href: "/documents",
    icon: Upload,
  },
  {
    title: "Chat",
    description: "Ask questions about your documents",
    href: "/chat",
    icon: MessageSquare,
  },
  {
    title: "Knowledge Graph",
    description: "Visualize connections between concepts",
    href: "/knowledge",
    icon: Network,
  },
  {
    title: "Documents",
    description: "Manage your uploaded documents",
    href: "/documents",
    icon: FileText,
  },
] as const;

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <>
      <MobileHeader title="Dashboard" />
      <div className="flex-1 space-y-6 p-4 lg:p-8">
        {/* Greeting */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight lg:text-3xl">
            Welcome back{user?.full_name ? `, ${user.full_name}` : ""}
          </h1>
          <p className="mt-1 text-muted-foreground">
            Your intelligent knowledge assistant is ready.
          </p>
        </div>

        {/* Quick Actions Grid */}
        <div className="grid gap-4 sm:grid-cols-2">
          {QUICK_ACTIONS.map((action) => (
            <Link key={action.href + action.title} href={action.href}>
              <Card className="transition-colors hover:bg-muted/50">
                <CardHeader className="flex flex-row items-center gap-3 space-y-0">
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <action.icon className="size-5" />
                  </div>
                  <div className="min-w-0">
                    <CardTitle className="text-base">
                      {action.title}
                    </CardTitle>
                    <CardDescription className="text-sm">
                      {action.description}
                    </CardDescription>
                  </div>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>

        {/* Stats placeholder -- will be populated in later waves */}
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            { label: "Documents", value: "--" },
            { label: "Knowledge Nodes", value: "--" },
            { label: "Chat Sessions", value: "--" },
          ].map((stat) => (
            <Card key={stat.label}>
              <CardHeader>
                <CardDescription>{stat.label}</CardDescription>
                <CardTitle className="text-3xl">{stat.value}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}
