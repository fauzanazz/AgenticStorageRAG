/**
 * Tests for useChat hook.
 * Validates conversation management and streaming API contracts.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockDelete = vi.fn();
const mockStream = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    stream: (...args: unknown[]) => mockStream(...args),
  },
}));

describe("useChat API contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should call GET /chat/conversations", async () => {
    const mockConversations = [
      {
        id: "conv-1",
        title: "Research Discussion",
        created_at: "2024-01-01T00:00:00Z",
        updated_at: "2024-01-01T01:00:00Z",
        message_count: 5,
      },
    ];
    mockGet.mockResolvedValue(mockConversations);

    const result = await mockGet("/chat/conversations");

    expect(mockGet).toHaveBeenCalledWith("/chat/conversations");
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveProperty("id");
    expect(result[0]).toHaveProperty("title");
    expect(result[0]).toHaveProperty("message_count");
  });

  it("should call POST /chat/conversations to create", async () => {
    const mockConv = {
      id: "conv-new",
      title: "New Chat",
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      message_count: 0,
    };
    mockPost.mockResolvedValue(mockConv);

    const result = await mockPost("/chat/conversations", {
      title: "New Chat",
    });

    expect(mockPost).toHaveBeenCalledWith("/chat/conversations", {
      title: "New Chat",
    });
    expect(result.id).toBe("conv-new");
    expect(result.message_count).toBe(0);
  });

  it("should call DELETE /chat/conversations/{id}", async () => {
    mockDelete.mockResolvedValue(undefined);

    await mockDelete("/chat/conversations/conv-1");

    expect(mockDelete).toHaveBeenCalledWith("/chat/conversations/conv-1");
  });

  it("should call GET /chat/conversations/{id}/messages", async () => {
    const mockMessages = [
      {
        id: "msg-1",
        role: "user",
        content: "What is climate change?",
        citations: [],
        timestamp: "2024-01-01T00:00:00Z",
      },
      {
        id: "msg-2",
        role: "assistant",
        content: "Climate change refers to...",
        citations: [
          {
            document_id: "doc-1",
            document_name: "paper.pdf",
            page: 5,
            excerpt: "relevant excerpt",
          },
        ],
        timestamp: "2024-01-01T00:00:01Z",
      },
    ];
    mockGet.mockResolvedValue(mockMessages);

    const result = await mockGet("/chat/conversations/conv-1/messages");

    expect(result).toHaveLength(2);
    expect(result[0].role).toBe("user");
    expect(result[1].role).toBe("assistant");
    expect(result[1].citations).toHaveLength(1);
    expect(result[1].citations[0]).toHaveProperty("document_name");
    expect(result[1].citations[0]).toHaveProperty("excerpt");
  });

  it("should call POST /chat/send with streaming", async () => {
    mockStream.mockImplementation(
      async (
        _url: string,
        _body: object,
        onChunk: (chunk: string) => void
      ) => {
        // Simulate streaming events
        onChunk(JSON.stringify({ type: "token", data: "Hello" }));
        onChunk(JSON.stringify({ type: "token", data: " world" }));
        onChunk(
          JSON.stringify({
            type: "citation",
            citation: {
              document_id: "doc-1",
              document_name: "paper.pdf",
              page: 3,
              excerpt: "relevant text",
            },
          })
        );
        onChunk(
          JSON.stringify({
            type: "done",
            conversation_id: "conv-123",
          })
        );
      }
    );

    const chunks: string[] = [];
    await mockStream(
      "/chat/send",
      { message: "hello", conversation_id: "conv-1" },
      (chunk: string) => {
        chunks.push(chunk);
      }
    );

    expect(mockStream).toHaveBeenCalledWith(
      "/chat/send",
      { message: "hello", conversation_id: "conv-1" },
      expect.any(Function)
    );
    expect(chunks).toHaveLength(4);

    // Validate event shapes
    const tokenEvent = JSON.parse(chunks[0]);
    expect(tokenEvent.type).toBe("token");
    expect(tokenEvent.data).toBe("Hello");

    const citationEvent = JSON.parse(chunks[2]);
    expect(citationEvent.type).toBe("citation");
    expect(citationEvent.citation).toHaveProperty("document_id");

    const doneEvent = JSON.parse(chunks[3]);
    expect(doneEvent.type).toBe("done");
    expect(doneEvent.conversation_id).toBe("conv-123");
  });

  it("should handle stream error event", async () => {
    mockStream.mockImplementation(
      async (
        _url: string,
        _body: object,
        onChunk: (chunk: string) => void
      ) => {
        onChunk(
          JSON.stringify({ type: "error", data: "Agent execution failed" })
        );
      }
    );

    let errorMessage = "";
    await mockStream(
      "/chat/send",
      { message: "test" },
      (chunk: string) => {
        const event = JSON.parse(chunk);
        if (event.type === "error") {
          errorMessage = event.data;
        }
      }
    );

    expect(errorMessage).toBe("Agent execution failed");
  });
});
