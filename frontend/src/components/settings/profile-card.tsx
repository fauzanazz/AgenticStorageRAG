"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type User } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";
import { queryKeys } from "@/lib/query-keys";
import { User as UserIcon, Check, Loader2 } from "lucide-react";

interface ProfileCardProps {
  user: User | null;
}

export function ProfileCard({ user }: ProfileCardProps) {
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState(user?.full_name || "");

  const updateProfileMutation = useMutation({
    mutationFn: (name: string) =>
      apiClient.patch<User>("/auth/me", { full_name: name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.auth.me() });
      setTimeout(() => updateProfileMutation.reset(), 3_000);
    },
  });

  const hasChanges = fullName.trim() !== (user?.full_name || "");
  const isSaving = updateProfileMutation.isPending;
  const saveSuccess = updateProfileMutation.isSuccess;
  const saveError = updateProfileMutation.error?.message ?? null;

  const handleSave = () => {
    if (!fullName.trim()) return;
    updateProfileMutation.mutate(fullName.trim());
  };

  const inputClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-foreground placeholder:text-outline-variant outline-none focus:ring-2 focus:ring-primary/50 transition-all";
  const inputStyle = {
    background: "var(--surface-container-high)",
    border: "1px solid var(--outline-variant)",
  };

  return (
    <div
      className="rounded-2xl p-6"
      style={{
        background: "var(--card)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-center gap-3 mb-6">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: "var(--accent)" }}
        >
          <UserIcon className="size-4" style={{ color: "var(--primary)" }} />
        </div>
        <h2 className="text-base font-semibold">Profile</h2>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="settings-fullname" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
            Full Name
          </label>
          <input
            id="settings-fullname"
            type="text"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your name"
            className={inputClassName}
            style={inputStyle}
          />
        </div>
        <div className="space-y-2">
          <label htmlFor="settings-email" className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
            Email Address
          </label>
          <input
            id="settings-email"
            type="email"
            defaultValue={user?.email || ""}
            placeholder="you@example.com"
            disabled
            className={`${inputClassName} opacity-50 cursor-not-allowed`}
            style={inputStyle}
          />
          <p className="text-xs" style={{ color: "var(--outline)" }}>
            Email cannot be changed.
          </p>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={!hasChanges || isSaving}
          className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          style={{ background: "var(--primary)" }}
        >
          {isSaving ? (
            <Loader2 className="size-4 animate-spin" />
          ) : saveSuccess ? (
            <Check className="size-4" />
          ) : null}
          {isSaving ? "Saving..." : saveSuccess ? "Saved" : "Save Changes"}
        </button>

        {saveError && (
          <span className="text-xs" style={{ color: "var(--destructive)" }}>
            {saveError}
          </span>
        )}
      </div>
    </div>
  );
}
