/**
 * Typed query key factory.
 *
 * Rules:
 *  - Every domain is a top-level namespace (object with an `all` tuple).
 *  - Nested keys narrow the cache scope so that invalidating a parent
 *    automatically covers all children.
 *  - Mutation side-effects call `queryClient.invalidateQueries({ queryKey: keys.X.all })`
 *    to prevent stale data after any CRUD operation.
 *
 * Pattern: { all, lists, list, detail, ... }
 *   all    → ["documents"]               — invalidate everything in the namespace
 *   lists  → ["documents", "list"]       — invalidate all list variants
 *   list   → ["documents", "list", args] — a specific list (e.g. page/filters)
 *   detail → ["documents", "detail", id] — a single resource by ID
 */

export const queryKeys = {
  // ── Documents ─────────────────────────────────────────────────────────────
  documents: {
    all: ["documents"] as const,
    lists: () => ["documents", "list"] as const,
    list: (page: number, pageSize: number, source?: string) =>
      ["documents", "list", { page, pageSize, source }] as const,
    stats: () => ["documents", "stats"] as const,
    driveTree: () => ["documents", "drive-tree"] as const,
  },

  // ── Chat ──────────────────────────────────────────────────────────────────
  conversations: {
    all: ["conversations"] as const,
    lists: () => ["conversations", "list"] as const,
    messages: (conversationId: string) =>
      ["conversations", "messages", conversationId] as const,
  },

  // ── Knowledge ─────────────────────────────────────────────────────────────
  knowledge: {
    all: ["knowledge"] as const,
    graph: (params?: {
      document_id?: string;
      entity_types?: string;
      limit?: number;
      source?: string;
    }) => ["knowledge", "graph", params ?? {}] as const,
    stats: () => ["knowledge", "stats"] as const,
    search: (query: string, vectorWeight: number) =>
      ["knowledge", "search", { query, vectorWeight }] as const,
  },

  // ── Ingestion (admin) ─────────────────────────────────────────────────────
  ingestion: {
    all: ["ingestion"] as const,
    jobs: (page: number) => ["ingestion", "jobs", { page }] as const,
    stats: () => ["ingestion", "stats"] as const,
    cost: () => ["ingestion", "cost"] as const,
    providers: () => ["ingestion", "providers"] as const,
    driveFolders: (parentId: string) =>
      ["ingestion", "drive-folders", { parentId }] as const,
    defaultFolder: () => ["ingestion", "default-folder"] as const,
  },

  // ── Auth ──────────────────────────────────────────────────────────────────
  auth: {
    all: ["auth"] as const,
    me: () => ["auth", "me"] as const,
  },
} as const;
