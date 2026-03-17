"use client";

import { useEffect, useRef } from "react";
import type { GraphVisualization } from "@/types/knowledge";

// Entity type colors
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

interface GraphCanvasProps {
  data: GraphVisualization;
  className?: string;
}

/**
 * Simple force-directed graph visualization using Canvas.
 *
 * Uses basic force simulation without external libraries.
 * For production, consider integrating d3-force or react-force-graph.
 */
export function GraphCanvas({ data, className }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.nodes.length === 0) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Set canvas size to container
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * window.devicePixelRatio;
    canvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    const width = rect.width;
    const height = rect.height;

    // Initialize node positions
    const positions = new Map<
      string,
      { x: number; y: number; vx: number; vy: number }
    >();

    data.nodes.forEach((node) => {
      positions.set(node.id, {
        x: Math.random() * width * 0.8 + width * 0.1,
        y: Math.random() * height * 0.8 + height * 0.1,
        vx: 0,
        vy: 0,
      });
    });

    // Simple force simulation
    function simulate() {
      const nodes = Array.from(positions.entries());
      const damping = 0.9;
      const repulsion = 2000;
      const attraction = 0.01;
      const centerForce = 0.005;

      // Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const [, a] = nodes[i];
          const [, b] = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
          const force = repulsion / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }
      }

      // Attraction along edges
      data.edges.forEach((edge) => {
        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const force = attraction;
        a.vx += dx * force;
        a.vy += dy * force;
        b.vx -= dx * force;
        b.vy -= dy * force;
      });

      // Center gravity
      nodes.forEach(([, pos]) => {
        pos.vx += (width / 2 - pos.x) * centerForce;
        pos.vy += (height / 2 - pos.y) * centerForce;
        pos.x += pos.vx;
        pos.y += pos.vy;
        pos.vx *= damping;
        pos.vy *= damping;
        // Clamp to bounds
        pos.x = Math.max(20, Math.min(width - 20, pos.x));
        pos.y = Math.max(20, Math.min(height - 20, pos.y));
      });
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, width, height);

      // Draw edges
      ctx.strokeStyle = "rgba(255,255,255,0.1)";
      ctx.lineWidth = 1;
      data.edges.forEach((edge) => {
        const a = positions.get(edge.source);
        const b = positions.get(edge.target);
        if (!a || !b) return;

        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();

        // Edge label
        const midX = (a.x + b.x) / 2;
        const midY = (a.y + b.y) / 2;
        ctx.fillStyle = "rgba(255,255,255,0.3)";
        ctx.font = "10px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(edge.label, midX, midY - 4);
      });

      // Draw nodes
      data.nodes.forEach((node) => {
        const pos = positions.get(node.id);
        if (!pos) return;

        const radius = 8 + (node.size || 1) * 3;
        const color = getColor(node.type);

        // Node circle
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,0.1)";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Node label
        ctx.fillStyle = "#f9fafb";
        ctx.font = "12px sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(node.label, pos.x, pos.y + radius + 14);
      });
    }

    // Run simulation
    let frame: number;
    let iterations = 0;
    const maxIterations = 200;

    function tick() {
      simulate();
      draw();
      iterations++;
      if (iterations < maxIterations) {
        frame = requestAnimationFrame(tick);
      }
    }

    tick();

    return () => {
      cancelAnimationFrame(frame);
    };
  }, [data]);

  if (data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-lg font-medium" style={{ color: "rgba(255,255,255,0.4)" }}>No graph data</p>
          <p className="text-sm" style={{ color: "rgba(255,255,255,0.3)" }}>Upload and process documents to build the knowledge graph</p>
        </div>
      </div>
    );
  }

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full ${className || ""}`}
      style={{ display: "block" }}
    />
  );
}
