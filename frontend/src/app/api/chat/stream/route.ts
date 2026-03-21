import { streamClaudeAgent } from "@/lib/claude-agent/agent";
import type { StreamRequest } from "@/lib/claude-agent/types";

export const maxDuration = 300;

export async function POST(request: Request) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return new Response("Unauthorized", { status: 401 });
  }

  const body = (await request.json()) as StreamRequest;
  const stream = await streamClaudeAgent(body, authHeader);

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
