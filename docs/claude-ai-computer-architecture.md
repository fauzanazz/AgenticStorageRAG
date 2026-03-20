# How Claude.ai Gets Its "Computer" -- The Full Architecture

Claude the model is just a text generator. It can't touch files, run code, or deploy anything. What gives it "computer-like" abilities is a **multi-layered infrastructure** that Anthropic built around it. Here's the complete picture:

---

## 1. The Core Pattern: Tool Use + Agent Loop

At the foundation, it's deceptively simple. Claude.ai (and Claude Code) are **a `while` loop around the Messages API with tool use**:

```
while stop_reason != "end_turn":
    response = claude.messages.create(tools=[...])
    for tool_call in response:
        result = execute(tool_call)  # harness runs the tool
        feed_result_back_to_claude(result)
```

The model outputs structured JSON saying "I want to call tool X with args Y." The **harness** (the software wrapping Claude) executes it and feeds back the result. Claude never touches the real world — the harness does.

---

## 2. The Code Execution Sandbox (API: `code_execution_20250825`)

When you use Claude.ai's "analysis tool" or the API's code execution, here's what actually spins up:

### Container Specs

| Resource | Value |
|----------|-------|
| Python | 3.11.12 |
| OS | Linux (x86_64/AMD64) |
| RAM | 5 GiB |
| Disk | 5 GiB workspace |
| CPU | 1 vCPU |
| Network | **Completely disabled** |
| Lifetime | 30 days, then expires |

### What's Inside

- **Two sub-tools** are injected automatically:
  - `bash_code_execution` — run any shell command
  - `text_editor_code_execution` — create/view/edit files (view, create, str_replace commands)
- **Pre-installed Python libraries**: pandas, numpy, scipy, scikit-learn, matplotlib, seaborn, sympy, pillow, openpyxl, python-pptx, python-docx, pypdf, reportlab, and more
- **System utilities**: ripgrep, fd, sqlite, unzip, 7zip, bc

### File I/O Flow

1. **Files in**: Upload via Files API → referenced with `container_upload` content block → files appear in the sandbox filesystem
2. **Files out**: Claude saves to `/tmp/whatever.png` → the response includes `file_id` references → you download via Files API
3. **Container reuse**: The response includes a `container.id` — pass it back in subsequent requests to maintain filesystem state across turns

### Security Model

- No internet access whatsoever
- Filesystem scoped to workspace only
- Full isolation from host and other containers
- OS-level enforcement (Linux bubblewrap / gVisor)

---

## 3. Claude Code on the Web — Firecracker MicroVMs ("Antspace")

When you use **Claude Code on the web** (where it clones your repo and works on it), it's a completely different, much beefier environment:

### The VM (reverse-engineered by AprilNEA)

| Resource | Value |
|----------|-------|
| Virtualization | **Firecracker microVMs** (same tech as AWS Lambda) |
| CPU | 4 vCPUs (Intel Xeon Cascade Lake @ 2.80GHz) |
| RAM | 16 GB |
| Disk | 252 GB |
| Kernel | Linux 6.18.5 |
| Init system | Custom `/process_api` binary (PID 1) — no systemd, no SSH, no cron |

### Process Architecture

```
PID 1: /process_api          <- Custom init + WebSocket API gateway (ports 2024, 2025)
PID 517: environment-runner   <- 27MB Go binary, manages sessions
PID 532: claude               <- The Claude CLI itself
```

The `environment-runner` binary was compiled from Anthropic's private monorepo (`github.com/anthropics/anthropic/api-go/environment-manager/`) and was found **unstripped with full debug symbols**, revealing the entire internal architecture.

### Key Internal Components (from debug symbols)

- **API Client**: Session ingress, work polling, retry logic
- **Auth**: GitHub app token provider integration
- **Claude Management**: Installation, upgrades, execution
- **Session Config**: Modes include new, resume, resume-cached, setup-only
- **Environment Types**: Anthropic-hosted and BYOC (Bring Your Own Cloud)
- **Git Proxy**: Credential proxy server for repository operations
- **MCP Servers**: Codesign and Supabase integration tools
- **WebSocket Tunnel**: Real-time communication with action handlers (deploy, file snapshot, status)

### Key Dependencies

- Internal Anthropic Go SDK
- Gorilla WebSocket for tunnel communication
- MCP Go v0.37.0 (Model Context Protocol)
- DataDog for metrics
- OpenTelemetry v1.39.0 for distributed tracing
- gRPC v1.79.0 for session routing

### Isolation Stack (from Woohyuk Choi's research)

```
+----------------------------------+
|  Claude CLI (agent loop)         |  <- generates tool calls
+----------------------------------+
|  Docker container                |  <- filesystem namespace isolation
+----------------------------------+
|  gVisor (runsc)                  |  <- syscall interception in userspace
+----------------------------------+
|  Google Compute Engine VM        |  <- hypervisor-level isolation
+----------------------------------+
|  Firecracker microVM             |  <- lightweight VM boundary
+----------------------------------+
```

- Filesystem mounted via **9p protocol** with remote caching (ephemeral)
- Only authenticated HTTPS through a proxy — no raw TCP/SSH
- Missing `CAP_SYS_ADMIN` and `CAP_NET_ADMIN` capabilities
- No nested virtualization

---

## 4. "Baku" — The Web App Builder

When you ask Claude.ai to build a web app, a special environment called **Baku** launches:

- **Stack**: Vite + React + TypeScript
- **Template**: `/opt/baku-templates/vite-template`
- **Dev server**: Managed via supervisord, logs to `/tmp/vite-dev.log`
- **Database**: Auto-provisions Supabase via 6 MCP tools:
  1. `provision_database` — on-demand Supabase project creation
  2. `execute_query` — SQL execution
  3. `apply_migration` — versioned schema changes with auto type generation
  4. `list_migrations` — migration history
  5. `generate_types` — TypeScript type regeneration from schema
  6. `deploy_function` — Supabase Edge Function deployment
- **Environment variables** auto-injected into `.env.local`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- **Deployment**: Routes to **Antspace** (Anthropic's own PaaS) by default, with Vercel as an alternative
- **Session protection**: Pre-stop hooks prevent termination if there are uncommitted changes, vite errors, or TypeScript compilation failures
- **Internal organization**:
  - Drafts: `.baku/drafts/`
  - Explorations: `.baku/explorations/`
  - Git author: `claude@anthropic.com`
  - Version control: local-only (no remote configured)

---

## 5. "Antspace" — Anthropic's Secret PaaS

This is Anthropic's undocumented deployment platform, a **Vercel competitor** they built internally:

### Deployment Protocol

```
POST /create  ->  Upload dist.tar.gz  ->  Stream NDJSON status
                                          (packaging -> uploading -> building -> deploying -> deployed)
```

### Antspace vs. Vercel Comparison

| Aspect | Vercel | Antspace |
|--------|--------|----------|
| Upload | SHA-based per-file dedup | Single tar.gz |
| Build | Remote | Local build, upload output |
| Status | Polling | Streaming NDJSON |
| Auth | API token + Team ID | Bearer token + dynamic control plane |
| Documentation | Public | Completely internal |

### BYOC: Bring Your Own Cloud

The environment-runner supports two environment types:

1. **anthropic** — Firecracker MicroVMs hosted by Anthropic
2. **byoc** — Customer-managed infrastructure with Anthropic orchestration

BYOC API Surface (7 Endpoints):
- `/v1/environments/whoami` — Identity discovery
- Work polling and acknowledgment — Job queue management
- Session context endpoints — Configuration retrieval
- Code signing — Binary verification
- Worker WebSocket — Real-time tunneling
- Supabase proxy — Database query relay

---

## 6. Claude.ai Artifacts (the "Analysis Tool" in the UI)

When Claude.ai generates an artifact (React component, HTML app, SVG, etc.):

- Runs in a **sandboxed iframe** with strict CSP headers
- Process isolation at the browser level
- `localStorage` access is restricted
- `fetch()` calls are governed by CSP
- The `window.claude.complete()` bridge allows artifact JS to send prompts back to Claude
- No code execution server-side — artifacts are pure client-side rendering

---

## 7. The Big Picture: Vertically Integrated AI Platform

```
User prompt
    |
    v
Claude Model (text generation + tool call decisions)
    |
    v
Harness / Agent Loop (while loop executing tool calls)
    |
    v
+------------------+-------------------+------------------+
| Code Execution   | Claude Code Web   | Baku (Web Apps)  |
| (API sandbox)    | (Firecracker VM)  | (Vite + React)   |
|                  |                   |                  |
| 1 CPU, 5GB RAM   | 4 CPU, 16GB RAM   | + Supabase MCP   |
| Python + Bash    | Full dev env      | + Antspace deploy |
| No network       | Proxy network     |                  |
+------------------+-------------------+------------------+
```

The key insight: **Claude itself has zero capabilities.** Every "skill" — file creation, code execution, deployment — is a tool that the surrounding harness provides. The model just decides *which* tools to call and *what arguments* to pass. The "computer" is entirely the infrastructure Anthropic built around the model.

This is why Claude Code (the CLI) works the same way — it calls `Read`, `Edit`, `Bash`, `Write` tools that the local harness executes. Same pattern, different environment.

---

## Sources

- [Code execution tool - Claude API Docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)
- [Anthropic's Hidden Vercel Competitor "Antspace" - AprilNEA](https://aprilnea.me/en/blog/reverse-engineering-claude-code-antspace)
- [Peeking Inside Claude Code on the Web's Sandbox - Woohyuk Choi](https://cw00h.github.io/posts/2025/10/claude-code-web-sandbox/)
- [Making Claude Code more secure and autonomous - Anthropic Engineering](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [How Anthropic built Artifacts - Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/how-anthropic-built-artifacts)
- [Sandbox Runtime - GitHub](https://github.com/anthropic-experimental/sandbox-runtime)
- [How tool use actually works in Claude Code](https://www.claudecodecamp.com/p/how-tool-use-actually-works-in-claude-code)
