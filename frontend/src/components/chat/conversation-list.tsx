"use client";

import { Plus, Trash2 } from "lucide-react";
import type { ChatSession } from "@/types/chat";

interface ConversationListProps {
  conversations: ChatSession[];
  activeId?: string;
  onSelect: (conversation: ChatSession) => void;
  onDelete: (conversationId: string) => void;
  onNew: () => void;
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onDelete,
  onNew,
}: ConversationListProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="p-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <button
          onClick={onNew}
          className="w-full h-10 rounded-xl text-sm font-semibold text-white flex items-center justify-center gap-2 transition-all hover:opacity-90"
          style={{ background: "linear-gradient(135deg, #6366F1, #A855F7)" }}
        >
          <Plus className="size-4" />
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="p-4 text-center text-sm" style={{ color: "rgba(255,255,255,0.3)" }}>
            No conversations yet
          </div>
        ) : (
          <div className="space-y-1 p-2">
            {conversations.map((conv) => (
              <div
                key={conv.id}
                className="group flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm transition-all"
                style={{
                  background: activeId === conv.id ? "rgba(99,102,241,0.12)" : "transparent",
                  color: activeId === conv.id ? "#818CF8" : "rgba(255,255,255,0.6)",
                }}
                onClick={() => onSelect(conv)}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{conv.title}</p>
                  <p className="text-xs" style={{ color: "rgba(255,255,255,0.3)" }}>
                    {conv.message_count} messages
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(conv.id);
                  }}
                  className="ml-2 opacity-0 transition-opacity group-hover:opacity-100 rounded-lg p-1 hover:bg-white/5"
                  style={{ color: "rgba(255,255,255,0.3)" }}
                  aria-label="Delete conversation"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
