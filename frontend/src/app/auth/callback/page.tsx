"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";
import { setAccessToken } from "@/lib/token-store";

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface OAuthTokenResponse {
  user: {
    id: string;
    email: string;
    full_name: string;
    is_active: boolean;
    is_admin: boolean;
    created_at: string;
  };
  tokens: AuthTokens;
}

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { refreshAuth } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      const params = new URLSearchParams(window.location.search);

      // Check for error in query params
      const errorParam = params.get("error");
      if (errorParam) {
        setError(errorParam);
        return;
      }

      // Exchange one-time code for tokens
      const code = params.get("code");
      if (!code) {
        setError("No authentication data received");
        return;
      }

      try {
        const response = await apiClient.post<OAuthTokenResponse>(
          "/auth/oauth/token",
          { code }
        );

        // Store access token in memory, refresh token in localStorage
        setAccessToken(response.tokens.access_token);
        localStorage.setItem("refresh_token", response.tokens.refresh_token);

        // Clean the URL
        window.history.replaceState(null, "", "/auth/callback");

        // Refresh auth state (will set access_token in memory)
        await refreshAuth();
        router.push("/");
      } catch {
        setError("Failed to complete authentication");
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
