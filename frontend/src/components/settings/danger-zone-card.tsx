import { Shield } from "lucide-react";

interface DangerZoneCardProps {
  onLogout: () => void;
}

export function DangerZoneCard({ onLogout }: DangerZoneCardProps) {
  return (
    <div
      className="rounded-2xl p-6"
      style={{
        background: "var(--error-container)",
        border: "1px solid color-mix(in srgb, var(--destructive) 15%, transparent)",
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: "var(--error-container)" }}
        >
          <Shield className="size-4" style={{ color: "var(--destructive)" }} />
        </div>
        <h2 className="text-base font-semibold" style={{ color: "var(--destructive)" }}>
          Danger Zone
        </h2>
      </div>
      <p className="text-sm mb-4" style={{ color: "var(--muted-foreground)" }}>
        Sign out of your account on this device.
      </p>
      <button
        onClick={onLogout}
        className="h-10 px-4 rounded-xl text-sm font-semibold transition-all hover:opacity-80"
        style={{
          background: "var(--error-container)",
          color: "var(--destructive)",
          border: "1px solid color-mix(in srgb, var(--destructive) 20%, transparent)",
        }}
      >
        Sign Out
      </button>
    </div>
  );
}
