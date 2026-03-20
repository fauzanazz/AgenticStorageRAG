"use client";

import { useMemo } from "react";
import { Streamdown, type Components, type AllowedTags } from "streamdown";
import { code } from "@streamdown/code";
import "streamdown/styles.css";
import type { ChatMessage, Citation } from "@/types/chat";
import { SourcesBar } from "@/components/chat/sources-bar";
import { ThinkingBlock } from "@/components/chat/thinking-block";
import { ToolCallBlock } from "@/components/chat/tool-call-block";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

/**
 * Transform `[N]` markers in text to `<citation ref="N"/>` custom tags
 * that streamdown will render via allowedTags.
 */
function injectCitationTags(content: string): string {
  return content.replace(/\[(\d+)\]/g, '<citation ref="$1"/>');
}

const ALLOWED_TAGS: AllowedTags = {
  citation: ["ref"],
};

function buildComponents(citations: Citation[]): Components {
  return {
    // Custom citation tag → clickable superscript
    citation: ({
      ref,
    }: {
      ref?: string;
      children?: React.ReactNode;
    }) => {
      const index = ref ? parseInt(ref, 10) - 1 : -1;
      const citation = index >= 0 ? citations[index] : undefined;
      const url = citation?.source_url;

      if (url) {
        return (
          <sup>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold no-underline transition-colors"
              style={{
                background: "var(--primary)",
                color: "white",
                marginLeft: "1px",
                marginRight: "1px",
                verticalAlign: "super",
              }}
              title={citation?.document_name || `Source ${ref}`}
            >
              {ref}
            </a>
          </sup>
        );
      }

      return (
        <sup
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold"
          style={{
            background: "var(--muted)",
            color: "var(--muted-foreground)",
            marginLeft: "1px",
            marginRight: "1px",
            verticalAlign: "super",
          }}
        >
          {ref}
        </sup>
      );
    },
    // Style overrides for prose
    p: ({ children, ...props }) => (
      <p className="mb-3 leading-relaxed last:mb-0" {...props}>
        {children}
      </p>
    ),
    a: ({ href, children, ...props }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2"
        style={{ color: "var(--primary)" }}
        {...props}
      >
        {children}
      </a>
    ),
    pre: ({ children, ...props }) => (
      <pre
        className="my-3 overflow-x-auto rounded-lg p-3 text-sm"
        style={{ background: "var(--card)", border: "1px solid var(--border)" }}
        {...props}
      >
        {children}
      </pre>
    ),
    ul: ({ children }) => (
      <ul className="mb-3 list-disc space-y-1 pl-5">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-3 list-decimal space-y-1 pl-5">{children}</ol>
    ),
    blockquote: ({ children }) => (
      <blockquote
        className="my-3 border-l-3 pl-3 italic"
        style={{
          borderColor: "var(--primary)",
          color: "var(--muted-foreground)",
        }}
      >
        {children}
      </blockquote>
    ),
    table: ({ children }) => (
      <div className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th
        className="border px-3 py-1.5 text-left text-xs font-semibold"
        style={{
          borderColor: "var(--border)",
          background: "var(--muted)",
        }}
      >
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td
        className="border px-3 py-1.5"
        style={{ borderColor: "var(--border)" }}
      >
        {children}
      </td>
    ),
  } as Components;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";

  const processedContent = useMemo(
    () => (isUser ? message.content : injectCitationTags(message.content)),
    [message.content, isUser],
  );

  const components = useMemo(
    () => buildComponents(message.citations),
    [message.citations],
  );

  const hasSteps = !isUser && message.steps && message.steps.length > 0;
  const hasContent = !!message.content;
  // Show loading indicator only when no steps and no content yet
  const showLoading = !isUser && !hasContent && !hasSteps && isStreaming;

  return (
    <div
      className={`flex w-full gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {/* AI Avatar */}
      {!isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ background: "var(--primary)" }}
        >
          AI
        </div>
      )}

      <div className={`max-w-[85%] space-y-1 ${isUser ? "items-end" : ""}`}>
        {/* Narrative steps — before the final answer */}
        {hasSteps && (
          <div className="mb-1">
            {message.steps.map((step, i) => {
              if (step.type === "thinking") {
                const isLastStep = i === message.steps.length - 1;
                return (
                  <ThinkingBlock
                    key={`thinking-${step.content?.slice(0, 20) ?? i}`}
                    content={step.content || ""}
                    isActive={isLastStep && isStreaming && !hasContent}
                  />
                );
              }
              if (step.type === "tool_call") {
                return <ToolCallBlock key={`tool-${step.tool_name}-${i}`} step={step} />;
              }
              return null;
            })}
          </div>
        )}

        {/* Sources bar — above assistant messages only */}
        {!isUser && message.citations.length > 0 && (
          <SourcesBar citations={message.citations} />
        )}

        {/* User bubble */}
        {isUser && (
          <div
            className="rounded-2xl rounded-br-md px-4 py-2.5 text-sm"
            style={{ background: "var(--primary)", color: "white" }}
          >
            {message.content || (
              <span style={{ color: "var(--outline-variant)" }}>...</span>
            )}
          </div>
        )}

        {/* Assistant content — no bubble, plain text */}
        {!isUser && hasContent && (
          <div className="text-sm" style={{ color: "#323035" }}>
            <Streamdown
              plugins={{ code }}
              allowedTags={ALLOWED_TAGS}
              components={components}
              isAnimating={isStreaming}
            >
              {processedContent}
            </Streamdown>
          </div>
        )}

        {/* Loading state — only when no steps and no content */}
        {showLoading && (
          <span className="text-sm" style={{ color: "var(--outline-variant)" }}>
            Thinking...
          </span>
        )}

        {/* Timestamp */}
        <p
          className="text-[10px]"
          style={{ color: "var(--outline-variant)" }}
        >
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>

      {/* User avatar */}
      {isUser && (
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
          style={{
            background: "var(--surface-container-high)",
            color: "#323035",
          }}
        >
          You
        </div>
      )}
    </div>
  );
}
