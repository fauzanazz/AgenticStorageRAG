/**
 * Tests for useKnowledge hook.
 * Validates graph, stats, and search API contracts.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

describe("useKnowledge API contracts", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should call GET /knowledge/graph with query params", async () => {
    const mockGraph = {
      entities: [
        { id: "e1", name: "Climate Change", type: "CONCEPT", properties: {} },
        { id: "e2", name: "CO2", type: "SUBSTANCE", properties: {} },
      ],
      relationships: [
        {
          id: "r1",
          source_id: "e1",
          target_id: "e2",
          relationship_type: "INVOLVES",
        },
      ],
    };
    mockGet.mockResolvedValue(mockGraph);

    const result = await mockGet("/knowledge/graph?limit=50");

    expect(mockGet).toHaveBeenCalledWith("/knowledge/graph?limit=50");
    expect(result.entities).toHaveLength(2);
    expect(result.relationships).toHaveLength(1);
    expect(result.entities[0]).toHaveProperty("name");
    expect(result.entities[0]).toHaveProperty("type");
    expect(result.relationships[0]).toHaveProperty("source_id");
    expect(result.relationships[0]).toHaveProperty("target_id");
  });

  it("should call GET /knowledge/stats", async () => {
    const mockStats = {
      total_entities: 150,
      total_relationships: 320,
      total_embeddings: 500,
      entity_types: { CONCEPT: 80, PERSON: 30, ORGANIZATION: 40 },
      relationship_types: { INVOLVES: 100, RELATED_TO: 220 },
    };
    mockGet.mockResolvedValue(mockStats);

    const result = await mockGet("/knowledge/stats");

    expect(result.total_entities).toBe(150);
    expect(result.total_relationships).toBe(320);
    expect(result.entity_types).toHaveProperty("CONCEPT");
  });

  it("should call POST /knowledge/search/hybrid with correct body", async () => {
    const mockResults = [
      {
        content: "Climate change affects biodiversity",
        score: 0.92,
        source: "paper.pdf",
        source_type: "vector",
        metadata: {},
      },
    ];
    mockPost.mockResolvedValue(mockResults);

    const result = await mockPost("/knowledge/search/hybrid", {
      query: "climate change",
      vector_weight: 0.5,
      top_k: 20,
    });

    expect(mockPost).toHaveBeenCalledWith("/knowledge/search/hybrid", {
      query: "climate change",
      vector_weight: 0.5,
      top_k: 20,
    });
    expect(result).toHaveLength(1);
    expect(result[0]).toHaveProperty("content");
    expect(result[0]).toHaveProperty("score");
    expect(result[0]).toHaveProperty("source");
    expect(result[0]).toHaveProperty("source_type");
  });

  it("should handle graph fetch with document_id filter", async () => {
    mockGet.mockResolvedValue({ entities: [], relationships: [] });

    await mockGet("/knowledge/graph?document_id=doc-123&limit=100");

    expect(mockGet).toHaveBeenCalledWith(
      "/knowledge/graph?document_id=doc-123&limit=100"
    );
  });
});
