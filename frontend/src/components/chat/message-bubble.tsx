"use client";

import type { ChatMessage, Citation } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <div
      className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs"
      style={{
        background: "rgba(99,102,241,0.1)",
        color: "#818CF8",
      }}
    >
      <span>
        {citation.document_name}
        {citation.page_number ? ` p.${citation.page_number}` : ""}
      </span>
      <span style={{ color: "rgba(129,140,248,0.5)" }}>
        ({Math.round(citation.relevance_score * 100)}%)
      </span>
    </div>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {/* AI Avatar */}
      {!isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
        >
          AI
        </div>
      )}

      <div className={`max-w-[85%] space-y-2 ${isUser ? "items-end" : ""}`}>
        {/* Message bubble */}
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser ? "rounded-br-md" : "rounded-bl-md"
          }`}
          style={
            isUser
              ? { background: "linear-gradient(135deg, #6366F1, #A855F7)", color: "white" }
              : { background: "rgba(255,255,255,0.05)", color: "rgba(255,255,255,0.85)" }
          }
        >
          {message.content || (
            <span className="animate-pulse" style={{ color: "rgba(255,255,255,0.4)" }}>
              Thinking...
            </span>
          )}
        </div>

        {/* Citations */}
        {message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {message.citations.map((citation, i) => (
              <CitationBadge key={i} citation={citation} />
            ))}
          </div>
        )}

        {/* Timestamp */}
        <p className="text-[10px]" style={{ color: "rgba(255,255,255,0.25)" }}>
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ background: "rgba(255,255,255,0.1)" }}
        >
          You
        </div>
      )}
    </div>
  );
}
