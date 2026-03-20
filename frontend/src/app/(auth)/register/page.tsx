"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const { register, loginWithOAuth } = useAuth();
  const [form, setForm] = useState({ fullName: "", email: "", password: "", confirmPassword: "" });
  const [error, setError] = useState("");
  const [status, setStatus] = useState<"idle" | "submitting" | "oauth">("idle");

  async function handleGoogleLogin() {
    setError("");
    setStatus("oauth");
    try {
      await loginWithOAuth("google");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to start Google sign-in");
      }
      setStatus("idle");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    if (form.password !== form.confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    setStatus("submitting");

    try {
      await register(form.email, form.password, form.fullName);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setStatus("idle");
    }
  }

  const inputClassName =
    "w-full h-12 rounded-xl px-4 text-sm placeholder:text-outline-variant outline-none focus:ring-2 focus:ring-primary/50 transition-all";
  const inputStyle = {
    background: "var(--muted)",
    border: "1px solid var(--outline-variant)",
  };

  return (
    <div className="w-full max-w-sm">
      {/* Mobile logo */}
      <div className="flex items-center gap-3 mb-8 lg:hidden">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg"
          style={{ background: "var(--primary)" }}
        >
          D
        </div>
        <span className="text-xl font-semibold tracking-tight" style={{ color: "var(--foreground)" }}>
          OpenRAG
        </span>
      </div>

      <h2 className="text-3xl font-bold mb-2" style={{ color: "var(--foreground)" }}>Create Account</h2>
      <p className="text-sm mb-8" style={{ color: "var(--muted-foreground)" }}>
        Get started with OpenRAG
      </p>

      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div
            className="rounded-xl px-4 py-3 text-sm"
            style={{
              background: "var(--error-container)",
              border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
              color: "var(--destructive)",
            }}
          >
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label
            htmlFor="fullName"
            className="block text-sm font-medium"
            style={{ color: "var(--on-surface-variant)" }}
          >
            Full Name
          </label>
          <input
            id="fullName"
            type="text"
            placeholder="Jane Doe"
            value={form.fullName}
            onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
            required
            autoComplete="name"
            className={inputClassName}
            style={inputStyle}
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor="email"
            className="block text-sm font-medium"
            style={{ color: "var(--on-surface-variant)" }}
          >
            Email Address
          </label>
          <input
            id="email"
            type="email"
            placeholder="you@example.com"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            required
            autoComplete="email"
            className={inputClassName}
            style={inputStyle}
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor="password"
            className="block text-sm font-medium"
            style={{ color: "var(--on-surface-variant)" }}
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            placeholder="At least 8 characters"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            required
            autoComplete="new-password"
            minLength={8}
            className={inputClassName}
            style={inputStyle}
          />
        </div>

        <div className="space-y-2">
          <label
            htmlFor="confirmPassword"
            className="block text-sm font-medium"
            style={{ color: "var(--on-surface-variant)" }}
          >
            Confirm Password
          </label>
          <input
            id="confirmPassword"
            type="password"
            placeholder="Repeat your password"
            value={form.confirmPassword}
            onChange={(e) => setForm((f) => ({ ...f, confirmPassword: e.target.value }))}
            required
            autoComplete="new-password"
            minLength={8}
            className={inputClassName}
            style={inputStyle}
          />
        </div>

        <button
          type="submit"
          disabled={status === "submitting"}
          className="w-full h-12 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{
            background: "var(--primary)",
          }}
        >
          {status === "submitting" ? "Creating account..." : "Create Account"}
        </button>

        <p className="text-center text-sm" style={{ color: "var(--muted-foreground)" }}>
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-medium hover:underline underline-offset-4"
            style={{ color: "var(--primary)" }}
          >
            Sign in
          </Link>
        </p>
      </form>

      {/* Divider */}
      <div className="flex items-center gap-4 my-6">
        <div className="flex-1 h-px" style={{ background: "var(--outline-variant)" }} />
        <span className="text-xs font-medium" style={{ color: "var(--muted-foreground)" }}>
          or
        </span>
        <div className="flex-1 h-px" style={{ background: "var(--outline-variant)" }} />
      </div>

      {/* Google OAuth */}
      <button
        type="button"
        onClick={handleGoogleLogin}
        disabled={status !== "idle"}
        className="w-full h-12 rounded-xl text-sm font-medium transition-all hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
        style={{
          background: "var(--muted)",
          border: "1px solid var(--outline-variant)",
          color: "var(--foreground)",
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24">
          <path
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
            fill="#4285F4"
          />
          <path
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
            fill="#34A853"
          />
          <path
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
            fill="#FBBC05"
          />
          <path
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
            fill="#EA4335"
          />
        </svg>
        {status === "oauth" ? "Redirecting..." : "Sign up with Google"}
      </button>
    </div>
  );
}
