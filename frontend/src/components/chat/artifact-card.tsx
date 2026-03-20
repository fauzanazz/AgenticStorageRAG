"use client";

interface ArtifactCardProps {
  title: string;
  type: string;
  onClick: () => void;
}

export function ArtifactCard({ title, type, onClick }: ArtifactCardProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 rounded-xl px-4 py-3 text-left text-sm transition-all hover:bg-black/[0.04] w-full"
      style={{
        border: "1px solid var(--border)",
        background: "var(--card)",
      }}
    >
      <div
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
        style={{ background: "var(--primary)", color: "white" }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-medium truncate">{title}</p>
        <p className="text-xs" style={{ color: "var(--muted-foreground)" }}>
          {type.charAt(0).toUpperCase() + type.slice(1)} document
        </p>
      </div>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        style={{ color: "var(--muted-foreground)", flexShrink: 0 }}
      >
        <path d="m9 18 6-6-6-6" />
      </svg>
    </button>
  );
}
