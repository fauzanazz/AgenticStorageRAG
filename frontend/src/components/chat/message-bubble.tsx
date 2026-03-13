"use client";

import { cn } from "@/lib/utils";
import type { ChatMessage, Citation } from "@/types/chat";

interface MessageBubbleProps {
  message: ChatMessage;
}

function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <div className="bg-muted inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs">
      <span className="text-muted-foreground">
        {citation.document_name}
        {citation.page_number ? ` p.${citation.page_number}` : ""}
      </span>
      <span className="text-muted-foreground/60">
        ({Math.round(citation.relevance_score * 100)}%)
      </span>
    </div>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn("flex w-full gap-3", isUser ? "justify-end" : "justify-start")}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="bg-primary text-primary-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium">
          AI
        </div>
      )}

      <div className={cn("max-w-[85%] space-y-2", isUser && "items-end")}>
        {/* Message bubble */}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
            isUser
              ? "bg-primary text-primary-foreground rounded-br-md"
              : "bg-muted rounded-bl-md"
          )}
        >
          {message.content || (
            <span className="text-muted-foreground animate-pulse">
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
        <p className="text-muted-foreground/60 text-[10px]">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="bg-secondary text-secondary-foreground flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium">
          You
        </div>
      )}
    </div>
  );
}
