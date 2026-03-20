import type { GraphCluster, GraphEdge, GraphNode } from "@/types/knowledge";

// ---------------------------------------------------------------------------
// Exported interfaces
// ---------------------------------------------------------------------------

interface ClusterTreeNode extends GraphCluster {
  children: string[]; // child cluster IDs
  totalNodeCount: number; // total leaf nodes in this cluster (recursive)
}

export interface FGNode {
  id: string;
  label: string;
  type: string;
  size: number;
  isCluster: boolean;
  clusterCount?: number;
}

interface FGLink {
  source: string;
  target: string;
  label: string;
  weight: number;
}

// ---------------------------------------------------------------------------
// buildClusterTree
// ---------------------------------------------------------------------------

export function buildClusterTree(clusters: GraphCluster[]): {
  tree: Map<string, ClusterTreeNode>;
  topLevelIds: string[];
} {
  // First pass: populate tree with empty children arrays
  const tree = new Map<string, ClusterTreeNode>();
  for (const cluster of clusters) {
    tree.set(cluster.id, { ...cluster, children: [], totalNodeCount: 0 });
  }

  // Second pass: wire up parent → child relationships
  const topLevelIds: string[] = [];
  for (const cluster of clusters) {
    const node = tree.get(cluster.id)!;
    if (cluster.parent_id === null) {
      topLevelIds.push(cluster.id);
    } else {
      const parent = tree.get(cluster.parent_id);
      if (parent) {
        parent.children.push(cluster.id);
      }
    }
    // Suppress the unused-variable lint for node; we already mutated via the map reference
    void node;
  }

  // Third pass: compute totalNodeCount bottom-up via DFS
  function computeCount(id: string): number {
    const node = tree.get(id);
    if (!node) return 0;

    if (node.children.length === 0) {
      // Leaf cluster — count direct node_ids
      node.totalNodeCount = node.node_ids.length;
    } else {
      // Intermediate cluster — sum children; also add any directly-owned nodes
      let count = node.node_ids.length;
      for (const childId of node.children) {
        count += computeCount(childId);
      }
      node.totalNodeCount = count;
    }
    return node.totalNodeCount;
  }

  for (const id of topLevelIds) {
    computeCount(id);
  }

  return { tree, topLevelIds };
}

// ---------------------------------------------------------------------------
// getNodeToClusterMap
// ---------------------------------------------------------------------------

/**
 * Returns a Map<leafNodeId, clusterIdAtTier>.
 *
 * Tier 1 — every leaf node maps to its top-level ancestor.
 * Tier 2 — every leaf node maps to its depth-1 (mid-level) cluster.
 *           If a top-level cluster has no children it maps to itself.
 * Tier 3 — empty map (nodes rendered individually).
 */
function getNodeToClusterMap(
  tier: 1 | 2 | 3,
  tree: Map<string, ClusterTreeNode>,
  topLevelIds: string[],
): Map<string, string> {
  const nodeToCluster = new Map<string, string>();

  if (tier === 3) return nodeToCluster;

  function walkTier1(clusterId: string, rootId: string) {
    const node = tree.get(clusterId);
    if (!node) return;
    for (const nodeId of node.node_ids) {
      nodeToCluster.set(nodeId, rootId);
    }
    for (const childId of node.children) {
      walkTier1(childId, rootId);
    }
  }

  function walkTier2(clusterId: string, tier2Id: string) {
    const node = tree.get(clusterId);
    if (!node) return;
    for (const nodeId of node.node_ids) {
      nodeToCluster.set(nodeId, tier2Id);
    }
    for (const childId of node.children) {
      walkTier2(childId, tier2Id);
    }
  }

  for (const topId of topLevelIds) {
    const topNode = tree.get(topId);
    if (!topNode) continue;

    if (tier === 1) {
      walkTier1(topId, topId);
    } else {
      // tier === 2
      if (topNode.children.length === 0) {
        // No mid-level children — map everything to this top-level cluster
        walkTier2(topId, topId);
      } else {
        // Map each depth-1 child subtree to that child
        for (const childId of topNode.children) {
          walkTier2(childId, childId);
        }
        // Also handle any direct node_ids on the top-level cluster itself
        for (const nodeId of topNode.node_ids) {
          nodeToCluster.set(nodeId, topId);
        }
      }
    }
  }

  return nodeToCluster;
}

// ---------------------------------------------------------------------------
// aggregateEdges
// ---------------------------------------------------------------------------

/**
 * Remaps edge endpoints using nodeToCluster, drops intra-cluster edges, and
 * merges duplicate cluster-to-cluster edges by summing weights.
 */
function aggregateEdges(
  edges: GraphEdge[],
  nodeToCluster: Map<string, string>,
): FGLink[] {
  // key → accumulated weight + representative label
  const merged = new Map<string, FGLink>();

  for (const edge of edges) {
    const src = nodeToCluster.get(edge.source) ?? edge.source;
    const tgt = nodeToCluster.get(edge.target) ?? edge.target;

    // Skip intra-cluster edges
    if (src === tgt) continue;

    // Canonical key (order-independent for undirected feel, but keep direction)
    const key = `${src}\0${tgt}\0${edge.label}`;
    const existing = merged.get(key);
    if (existing) {
      existing.weight += edge.weight;
    } else {
      merged.set(key, { source: src, target: tgt, label: edge.label, weight: edge.weight });
    }
  }

  return Array.from(merged.values());
}

// ---------------------------------------------------------------------------
// buildTierView
// ---------------------------------------------------------------------------

/**
 * Returns the node and link arrays suitable for react-force-graph-2d.
 */
export function buildTierView(
  tier: 1 | 2 | 3,
  tree: Map<string, ClusterTreeNode>,
  topLevelIds: string[],
  nodes: GraphNode[],
  edges: GraphEdge[],
): { nodes: FGNode[]; links: FGLink[] } {
  // ---- Tier 3: render every leaf node individually ----
  if (tier === 3) {
    const fgNodes: FGNode[] = nodes.map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type,
      size: n.size,
      isCluster: false,
    }));
    const fgLinks: FGLink[] = edges.map((e) => ({
      source: e.source,
      target: e.target,
      label: e.label,
      weight: e.weight,
    }));
    return { nodes: fgNodes, links: fgLinks };
  }

  // ---- Tier 1 / 2: cluster view ----
  const nodeToCluster = getNodeToClusterMap(tier, tree, topLevelIds);

  // Determine which clusters are active at this tier
  const activeClusters = new Set<string>();
  for (const tier1Id of topLevelIds) {
    const topNode = tree.get(tier1Id);
    if (!topNode) continue;

    if (tier === 1) {
      activeClusters.add(tier1Id);
    } else {
      // tier 2: depth-1 children, or top-level if no children
      if (topNode.children.length === 0) {
        activeClusters.add(tier1Id);
      } else {
        for (const childId of topNode.children) {
          activeClusters.add(childId);
        }
        // If top-level also directly owns nodes, include it as a cluster node too
        if (topNode.node_ids.length > 0) {
          activeClusters.add(tier1Id);
        }
      }
    }
  }

  // Build a lookup from nodeId → GraphNode for type resolution
  const nodeById = new Map<string, GraphNode>();
  for (const n of nodes) {
    nodeById.set(n.id, n);
  }

  // Helper: find the most common type among a set of leaf node IDs
  function dominantType(nodeIds: Iterable<string>): string {
    const freq = new Map<string, number>();
    for (const id of nodeIds) {
      const n = nodeById.get(id);
      if (!n) continue;
      freq.set(n.type, (freq.get(n.type) ?? 0) + 1);
    }
    let best = "unknown";
    let bestCount = 0;
    for (const [type, count] of freq) {
      if (count > bestCount) {
        best = type;
        bestCount = count;
      }
    }
    return best;
  }

  // Collect all leaf node IDs that belong to a cluster (recursively)
  function collectLeafIds(clusterId: string): string[] {
    const clusterNode = tree.get(clusterId);
    if (!clusterNode) return [];
    if (clusterNode.children.length === 0) return [...clusterNode.node_ids];
    const ids: string[] = [...clusterNode.node_ids];
    for (const childId of clusterNode.children) {
      ids.push(...collectLeafIds(childId));
    }
    return ids;
  }

  const fgNodes: FGNode[] = [];
  const clusteredNodeIds = new Set<string>(nodeToCluster.keys());

  // Emit cluster FGNodes
  for (const clusterId of activeClusters) {
    const clusterNode = tree.get(clusterId);
    if (!clusterNode) continue;

    const leafIds = collectLeafIds(clusterId);
    const count = clusterNode.totalNodeCount > 0 ? clusterNode.totalNodeCount : leafIds.length;
    const type = dominantType(leafIds);

    fgNodes.push({
      id: clusterId,
      label: `${clusterNode.label} (${count})`,
      type,
      size: count,
      isCluster: true,
      clusterCount: count,
    });
  }

  // Emit unclustered individual nodes
  for (const n of nodes) {
    if (!clusteredNodeIds.has(n.id)) {
      fgNodes.push({
        id: n.id,
        label: n.label,
        type: n.type,
        size: n.size,
        isCluster: false,
      });
    }
  }

  const fgLinks = aggregateEdges(edges, nodeToCluster);

  return { nodes: fgNodes, links: fgLinks };
}
