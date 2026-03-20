import { Bell } from "lucide-react";

export function PreferencesCard() {
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
          style={{ background: "#f3e5f5" }}
        >
          <Bell className="size-4" style={{ color: "var(--tertiary)" }} />
        </div>
        <h2 className="text-base font-semibold">Preferences</h2>
      </div>

      <div className="space-y-4">
        {["Email Notifications", "Auto-process Documents", "Show Citations in Chat"].map(
          (pref) => (
            <div key={pref} className="flex items-center justify-between">
              <span className="text-sm" style={{ color: "var(--on-surface-variant)" }}>
                {pref}
              </span>
              <div
                className="w-11 h-6 rounded-full relative cursor-pointer"
                style={{ background: "color-mix(in srgb, var(--primary) 30%, transparent)" }}
              >
                <div
                  className="w-5 h-5 rounded-full absolute top-0.5 right-0.5"
                  style={{ background: "var(--primary)" }}
                />
              </div>
            </div>
          )
        )}
      </div>
      <p className="mt-4 text-xs" style={{ color: "var(--outline-variant)" }}>
        Preference toggles are coming soon.
      </p>
    </div>
  );
}
