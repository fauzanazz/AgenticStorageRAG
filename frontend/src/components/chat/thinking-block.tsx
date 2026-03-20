"use client";

import { useEffect, useRef, useState } from "react";

interface ThinkingBlockProps {
  content: string;
  isActive?: boolean;
}

export function ThinkingBlock({ content, isActive }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(true);
  const wasActive = useRef(false);

  // Auto-collapse 3s after thinking finishes (active → inactive)
  useEffect(() => {
    if (isActive) {
      wasActive.current = true;
      return;
    }
    if (!wasActive.current) return;
    wasActive.current = false;
    const timer = setTimeout(() => setExpanded(false), 3000);
    return () => clearTimeout(timer);
  }, [isActive]);

  if (!content) return null;

  return (
    <div
      className="group mb-2 animate-in fade-in slide-in-from-bottom-1 duration-300"
      style={{ animationFillMode: "both" }}
    >
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider transition-colors hover:opacity-80"
        style={{ color: "var(--muted-foreground)" }}
      >
        {/* Thinking indicator */}
        <span className="relative flex h-3.5 w-3.5 items-center justify-center">
          {isActive ? (
            <>
              <span
                className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40"
                style={{ background: "var(--primary)" }}
              />
              <span
                className="relative inline-flex h-2 w-2 rounded-full"
                style={{ background: "var(--primary)" }}
              />
            </>
          ) : (
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 20h9" />
              <path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.855z" />
            </svg>
          )}
        </span>
        Thinking
        <svg
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          className={`transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      <div
        className="overflow-hidden transition-all duration-200 ease-out"
        style={{
          maxHeight: expanded ? "500px" : "0",
          opacity: expanded ? 1 : 0,
        }}
      >
        <p
          className="mt-1.5 whitespace-pre-wrap text-sm italic leading-relaxed"
          style={{ color: "var(--muted-foreground)" }}
        >
          {content}
        </p>
      </div>
    </div>
  );
}
