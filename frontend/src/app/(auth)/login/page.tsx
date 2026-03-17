"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setIsSubmitting(true);

    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-sm">
      {/* Mobile logo -- hidden on lg where the brand panel shows */}
      <div className="flex items-center gap-3 mb-8 lg:hidden">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg"
          style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
        >
          D
        </div>
        <span className="text-white text-xl font-semibold tracking-tight">
          DingDong RAG
        </span>
      </div>

      <h2 className="text-3xl font-bold text-white mb-2">Welcome back</h2>
      <p className="text-sm mb-8" style={{ color: "rgba(255,255,255,0.4)" }}>
        Enter your credentials to access your account
      </p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div
            className="rounded-xl px-4 py-3 text-sm"
            style={{
              background: "rgba(239,68,68,0.1)",
              border: "1px solid rgba(239,68,68,0.2)",
              color: "#FCA5A5",
            }}
          >
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label
            htmlFor="email"
            className="block text-sm font-medium"
            style={{ color: "rgba(255,255,255,0.6)" }}
          >
            Email Address
          </label>
          <input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            className="w-full h-12 rounded-xl px-4 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor="password"
            className="block text-sm font-medium"
            style={{ color: "rgba(255,255,255,0.6)" }}
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            minLength={8}
            className="w-full h-12 rounded-xl px-4 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
            style={{
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.08)",
            }}
          />
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-12 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: "linear-gradient(135deg, #6366F1, #A855F7)",
          }}
        >
          {isSubmitting ? "Signing in..." : "Sign In"}
        </button>

        <p className="text-center text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="font-medium hover:underline underline-offset-4"
            style={{ color: "#818CF8" }}
          >
            Sign up
          </Link>
        </p>
      </form>
    </div>
  );
}
