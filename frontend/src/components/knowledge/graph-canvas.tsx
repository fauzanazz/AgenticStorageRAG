/* eslint-disable @typescript-eslint/no-explicit-any -- react-force-graph-2d lacks TS types */
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { GraphVisualization } from "@/types/knowledge";
import { buildClusterTree, buildTierView } from "./cluster-utils";
import type { FGNode } from "./cluster-utils";

// Dynamic import — force-graph uses canvas APIs unavailable during SSR
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
}) as any;

// ── Entity type colors ───────────────────────────────────────────────────
const TYPE_COLORS: Record<string, string> = {
  Person: "#3b82f6",
  Organization: "#10b981",
  Concept: "#8b5cf6",
  Technology: "#f59e0b",
  Event: "#ef4444",
  Location: "#06b6d4",
  Document: "#f97316",
  Default: "#6b7280",
};

function getColor(type: string): string {
  return TYPE_COLORS[type] || TYPE_COLORS.Default;
}

// ── Zoom tier thresholds ─────────────────────────────────────────────────
const TIER1_MAX = 0.4;
const TIER2_MAX = 1.2;

function getTier(k: number): 1 | 2 | 3 {
  if (k < TIER1_MAX) return 1;
  if (k < TIER2_MAX) return 2;
  return 3;
}

// ── Component ────────────────────────────────────────────────────────────
interface GraphCanvasProps {
  data: GraphVisualization;
  className?: string;
  onExpandNode?: (nodeId: string) => Promise<GraphVisualization | null>;
}

export function GraphCanvas({ data, className, onExpandNode }: GraphCanvasProps) {
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [tier, setTier] = useState<1 | 2 | 3>(3);
  const skipNextZoomRef = useRef(false);

  const hasClusters = !!data.clusters?.length;

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setDimensions({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Build cluster tree
  const clusterTree = useMemo(() => {
    if (!hasClusters) return null;
    return buildClusterTree(data.clusters!);
  }, [data.clusters, hasClusters]);

  // Pre-compute all 3 tier views
  const tierViews = useMemo(() => {
    if (!clusterTree) {
      const flat = {
        nodes: data.nodes.map((n) => ({
          id: n.id,
          label: n.label,
          type: n.type,
          size: n.size || 1,
          isCluster: false as const,
        })),
        links: data.edges.map((e) => ({
          source: e.source,
          target: e.target,
          label: e.label,
          weight: e.weight,
        })),
      };
      return { 1: flat, 2: flat, 3: flat };
    }
    const { tree, topLevelIds } = clusterTree;
    return {
      1: buildTierView(1, tree, topLevelIds, data.nodes, data.edges),
      2: buildTierView(2, tree, topLevelIds, data.nodes, data.edges),
      3: buildTierView(3, tree, topLevelIds, data.nodes, data.edges),
    };
  }, [clusterTree, data.nodes, data.edges]);

  const graphData = tierViews[tier];

  // Zoom handler — switch tiers
  const onZoom = useCallback(
    ({ k }: { k: number }) => {
      if (skipNextZoomRef.current) {
        skipNextZoomRef.current = false;
        return;
      }
      if (!hasClusters) return;
      const newTier = getTier(k);
      if (newTier !== tier) {
        skipNextZoomRef.current = true;
        setTier(newTier);
      }
    },
    [tier, hasClusters]
  );

  // Custom node rendering
  const nodeCanvasObject = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const { x = 0, y = 0 } = node;
      const isCluster = (node as FGNode).isCluster ?? false;
      const radius = isCluster
        ? 6 + ((node as FGNode).clusterCount ?? 3) * 0.8
        : 4 + ((node as FGNode).size ?? 1) * 1.5;
      const color = getColor((node as FGNode).type ?? "Default");
      const label = (node as FGNode).label ?? node.id ?? "";
      const fontSize = Math.min(12 / globalScale, 5);

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = isCluster ? color + "cc" : color;
      ctx.fill();

      if (isCluster) {
        ctx.setLineDash([3 / globalScale, 2 / globalScale]);
        ctx.strokeStyle = "rgba(255,255,255,0.5)";
        ctx.lineWidth = 1.5 / globalScale;
        ctx.stroke();
        ctx.setLineDash([]);
      } else {
        ctx.strokeStyle = "rgba(255,255,255,0.15)";
        ctx.lineWidth = 0.5 / globalScale;
        ctx.stroke();
      }

      ctx.font = `${isCluster ? "bold " : ""}${fontSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.fillText(label, x, y + radius + 2 / globalScale);
    },
    []
  );

  // Hit area
  const nodePointerAreaPaint = useCallback(
    (node: any, color: string, ctx: CanvasRenderingContext2D) => {
      const { x = 0, y = 0 } = node;
      const isCluster = (node as FGNode).isCluster ?? false;
      const radius = isCluster
        ? 6 + ((node as FGNode).clusterCount ?? 3) * 0.8
        : 4 + ((node as FGNode).size ?? 1) * 1.5;
      ctx.beginPath();
      ctx.arc(x, y, radius + 2, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
    },
    []
  );

  if (data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-lg font-medium" style={{ color: "rgba(255,255,255,0.4)" }}>
            No graph data
          </p>
          <p className="text-sm" style={{ color: "rgba(255,255,255,0.3)" }}>
            Upload and process documents to build the knowledge graph
          </p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`relative w-full h-full ${className || ""}`}>
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        backgroundColor="rgba(0,0,0,0)"
        nodeCanvasObjectMode={() => "replace"}
        nodeCanvasObject={nodeCanvasObject}
        nodePointerAreaPaint={nodePointerAreaPaint}
        nodeVal={(node: any) =>
          (node as FGNode).isCluster ? ((node as FGNode).clusterCount ?? 3) * 2 : ((node as FGNode).size ?? 1)
        }
        linkColor={() => "#888"}
        linkWidth={1.5}
        linkLabel={(link: any) => link.label}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        onNodeClick={onExpandNode ? (node: any) => {
          if (!(node as FGNode).isCluster && node.id) onExpandNode(node.id);
        } : undefined}
        onZoom={hasClusters ? onZoom : undefined}
        minZoom={0.05}
        maxZoom={12}
        cooldownTicks={100}
        onEngineStop={() => fgRef.current?.zoomToFit(400, 40)}
      />

      {hasClusters && tier < 3 && (
        <div
          className="absolute bottom-3 left-3 rounded-lg px-2.5 py-1 text-[11px]"
          style={{
            background: "rgba(139,92,246,0.15)",
            border: "1px solid rgba(139,92,246,0.3)",
            color: "rgba(139,92,246,0.9)",
          }}
        >
          {tier === 1 ? "Top-level clusters" : "Sub-clusters"} ({graphData.nodes.length} groups, {data.nodes.length} nodes) — zoom in to expand
        </div>
      )}
    </div>
  );
}
