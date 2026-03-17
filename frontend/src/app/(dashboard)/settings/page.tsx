"use client";

import { useCallback, useState } from "react";
import { useAuth, type User } from "@/hooks/use-auth";
import { apiClient } from "@/lib/api-client";
import { User as UserIcon, Bell, Shield, Check, Loader2 } from "lucide-react";

export default function SettingsPage() {
  const { user, logout } = useAuth();

  const [fullName, setFullName] = useState(user?.full_name || "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSaveProfile = useCallback(async () => {
    if (!fullName.trim()) return;

    setIsSaving(true);
    setSaveError(null);
    setSaveSuccess(false);

    try {
      await apiClient.patch<User>("/auth/me", {
        full_name: fullName.trim(),
      });
      setSaveSuccess(true);
      // Auto-clear success message after 3s
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update profile");
    } finally {
      setIsSaving(false);
    }
  }, [fullName]);

  const hasChanges = fullName.trim() !== (user?.full_name || "");

  const inputClassName =
    "w-full h-12 rounded-xl px-4 text-sm text-white placeholder:text-white/30 outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all";
  const inputStyle = {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.08)",
  };

  return (
    <div className="flex-1 p-6 lg:p-8 space-y-8 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white tracking-tight">Settings</h1>
        <p className="mt-1 text-sm" style={{ color: "rgba(255,255,255,0.4)" }}>
          Manage your account preferences
        </p>
      </div>

      {/* Profile Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(99,102,241,0.12)" }}
          >
            <UserIcon className="size-4" style={{ color: "#818CF8" }} />
          </div>
          <h2 className="text-base font-semibold text-white">Profile</h2>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Full Name
            </label>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Your name"
              className={inputClassName}
              style={inputStyle}
            />
          </div>
          <div className="space-y-2">
            <label className="block text-sm font-medium" style={{ color: "rgba(255,255,255,0.6)" }}>
              Email Address
            </label>
            <input
              type="email"
              defaultValue={user?.email || ""}
              placeholder="you@example.com"
              disabled
              className={`${inputClassName} opacity-50 cursor-not-allowed`}
              style={inputStyle}
            />
            <p className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
              Email cannot be changed.
            </p>
          </div>
        </div>

        {/* Save button + feedback */}
        <div className="mt-6 flex items-center gap-3">
          <button
            onClick={handleSaveProfile}
            disabled={!hasChanges || isSaving}
            className="h-10 px-5 rounded-xl text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
            style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
          >
            {isSaving ? (
              <Loader2 className="size-4 animate-spin" />
            ) : saveSuccess ? (
              <Check className="size-4" />
            ) : null}
            {isSaving ? "Saving..." : saveSuccess ? "Saved" : "Save Changes"}
          </button>

          {saveError && (
            <span className="text-xs" style={{ color: "#FCA5A5" }}>
              {saveError}
            </span>
          )}
        </div>
      </div>

      {/* Preferences Section */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(168,85,247,0.12)" }}
          >
            <Bell className="size-4" style={{ color: "#C084FC" }} />
          </div>
          <h2 className="text-base font-semibold text-white">Preferences</h2>
        </div>

        <div className="space-y-4">
          {["Email Notifications", "Auto-process Documents", "Show Citations in Chat"].map(
            (pref) => (
              <div key={pref} className="flex items-center justify-between">
                <span className="text-sm" style={{ color: "rgba(255,255,255,0.6)" }}>
                  {pref}
                </span>
                <div
                  className="w-11 h-6 rounded-full relative cursor-pointer"
                  style={{ background: "rgba(99,102,241,0.3)" }}
                >
                  <div
                    className="w-5 h-5 rounded-full absolute top-0.5 right-0.5"
                    style={{ background: "#6366F1" }}
                  />
                </div>
              </div>
            )
          )}
        </div>
        <p className="mt-4 text-xs" style={{ color: "rgba(255,255,255,0.25)" }}>
          Preference toggles are coming soon.
        </p>
      </div>

      {/* Danger Zone */}
      <div
        className="rounded-2xl p-6"
        style={{
          background: "rgba(239,68,68,0.03)",
          border: "1px solid rgba(239,68,68,0.1)",
        }}
      >
        <div className="flex items-center gap-3 mb-4">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: "rgba(239,68,68,0.12)" }}
          >
            <Shield className="size-4" style={{ color: "#FCA5A5" }} />
          </div>
          <h2 className="text-base font-semibold" style={{ color: "#FCA5A5" }}>
            Danger Zone
          </h2>
        </div>
        <p className="text-sm mb-4" style={{ color: "rgba(255,255,255,0.4)" }}>
          Sign out of your account on this device.
        </p>
        <button
          onClick={logout}
          className="h-10 px-4 rounded-xl text-sm font-semibold transition-all hover:opacity-80"
          style={{
            background: "rgba(239,68,68,0.15)",
            color: "#FCA5A5",
            border: "1px solid rgba(239,68,68,0.2)",
          }}
        >
          Sign Out
        </button>
      </div>
    </div>
  );
}
