"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { refreshAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      // Check for error in query params
      const params = new URLSearchParams(window.location.search);
      const errorParam = params.get("error");
      if (errorParam) {
        setError(decodeURIComponent(errorParam));
        return;
      }

      // Parse tokens from URL fragment
      const hash = window.location.hash.substring(1); // remove #
      if (!hash) {
        setError("No authentication data received");
        return;
      }

      const fragment = new URLSearchParams(hash);
      const accessToken = fragment.get("access_token");
      const refreshToken = fragment.get("refresh_token");

      if (!accessToken || !refreshToken) {
        setError("Incomplete authentication data");
        return;
      }

      // Store tokens (same keys as existing auth)
      localStorage.setItem("access_token", accessToken);
      localStorage.setItem("refresh_token", refreshToken);

      // Clean the URL (remove tokens from address bar)
      window.history.replaceState(null, "", "/auth/callback");

      // Load user profile and update AuthProvider state
      try {
        await refreshAuth();
        router.push("/");
      } catch {
        setError("Failed to load user profile");
      }
    }

    handleCallback();
  }, [router, refreshAuth]);

  if (error) {
    return (
      <div className="w-full max-w-sm text-center">
        <div
          className="rounded-xl px-4 py-3 text-sm mb-6"
          style={{
            background: "var(--error-container)",
            border:
              "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
            color: "var(--destructive)",
          }}
        >
          {error}
        </div>
        <Link
          href="/login"
          className="text-sm font-medium hover:underline underline-offset-4"
          style={{ color: "var(--primary)" }}
        >
          Back to login
        </Link>
      </div>
    );
  }

  return (
    <div className="w-full max-w-sm text-center">
      <div className="flex items-center justify-center gap-3 mb-4">
        <div
          className="w-6 h-6 rounded-full border-2 border-t-transparent animate-spin"
          style={{
            borderColor: "var(--primary)",
            borderTopColor: "transparent",
          }}
        />
        <span
          className="text-sm"
          style={{ color: "var(--muted-foreground)" }}
        >
          Completing sign in...
        </span>
      </div>
    </div>
  );
}
