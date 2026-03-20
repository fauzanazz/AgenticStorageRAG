# Azure Ethos Design System Implementation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the entire frontend from the current dark indigo theme (`#0A0A0F` + `#6366F1`) to the Azure Ethos professional light design system (`#fcf8f9` + `#3557bc`), matching the Stitch wireframes.

**Architecture:** Theme-first approach — update CSS variables in `globals.css` first, then swap font from Inter to Plus Jakarta Sans, then update each component's hardcoded inline styles. The CSS variable layer handles ~40% of the change automatically; the remaining ~60% is hardcoded `style={{}}` props in components.

**Tech Stack:** Tailwind CSS v4, CSS custom properties, Plus Jakarta Sans (Google Fonts), Material Symbols Outlined (optional — keep Lucide for now)

---

## Design System Token Reference

### Colors (Azure Ethos)
| Token | Old Value | New Value |
|-------|-----------|-----------|
| `--background` | `#0A0A0F` | `#fcf8f9` |
| `--foreground` | `#FFFFFF` | `#323235` |
| `--card` | `rgba(255,255,255,0.03)` | `#ffffff` |
| `--card-foreground` | `#FFFFFF` | `#323235` |
| `--popover` | `#141428` | `#ffffff` |
| `--popover-foreground` | `#FFFFFF` | `#323235` |
| `--primary` | `#6366F1` | `#3557bc` |
| `--primary-foreground` | `#FFFFFF` | `#f8f7ff` |
| `--secondary` | `rgba(255,255,255,0.04)` | `#e4e2e6` |
| `--secondary-foreground` | `#FFFFFF` | `#323235` |
| `--muted` | `rgba(255,255,255,0.04)` | `#f0edef` |
| `--muted-foreground` | `rgba(255,255,255,0.4)` | `#5f5f62` |
| `--accent` | `rgba(99,102,241,0.12)` | `#dce1ff` |
| `--accent-foreground` | `#818CF8` | `#3557bc` |
| `--destructive` | `#EF4444` | `#9e3f4e` |
| `--border` | `rgba(255,255,255,0.06)` | `#b3b1b4` |
| `--input` | `rgba(255,255,255,0.08)` | `#b3b1b4` |
| `--ring` | `#6366F1` | `#3557bc` |
| `--sidebar` | `rgba(255,255,255,0.02)` | `#f6f3f4` |
| `--sidebar-foreground` | `#FFFFFF` | `#323235` |
| `--sidebar-primary` | `#6366F1` | `#3557bc` |
| `--sidebar-primary-foreground` | `#FFFFFF` | `#f8f7ff` |
| `--sidebar-accent` | `rgba(99,102,241,0.12)` | `#dce1ff` |
| `--sidebar-accent-foreground` | `#818CF8` | `#3557bc` |
| `--sidebar-border` | `rgba(255,255,255,0.06)` | `#b3b1b4` |
| `--sidebar-ring` | `#6366F1` | `#3557bc` |
| `--chart-1` | `#6366F1` | `#3557bc` |
| `--chart-2` | `#A855F7` | `#625b77` |
| `--chart-3` | `#22D3EE` | `#7190f8` |
| `--chart-4` | `#EC4899` | `#9e3f4e` |
| `--chart-5` | `#F59E0B` | `#5f5f62` |

### Surface Hierarchy (new Azure Ethos concept)
| Level | Token | Value |
|-------|-------|-------|
| Base | `surface` | `#fcf8f9` |
| Low | `surface-container-low` | `#f6f3f4` |
| Medium | `surface-container` | `#f0edef` |
| High | `surface-container-high` | `#eae7ea` |
| Highest | `surface-container-highest` | `#e4e2e5` |
| Lowest (cards) | `surface-container-lowest` | `#ffffff` |

### Typography
| Old | New |
|-----|-----|
| Inter (local woff2) | Plus Jakarta Sans (Google Fonts) |
| JetBrains Mono | JetBrains Mono (keep) |

### Inline Style Color Mapping Reference
These are the most common hardcoded colors in components that need replacing:

| Old Pattern | New Replacement |
|-------------|-----------------|
| `background: "#0A0A0F"` | `background: "#fcf8f9"` |
| `color: "white"` / `text-white` | `color: "#323235"` / `text-foreground` |
| `color: "rgba(255,255,255,0.4)"` | `color: "#5f5f62"` (muted-foreground) |
| `color: "rgba(255,255,255,0.3)"` | `color: "#7b7a7d"` (outline) |
| `color: "rgba(255,255,255,0.5)"` | `color: "#5f5f62"` (muted-foreground) |
| `color: "rgba(255,255,255,0.6)"` | `color: "#5f5f61"` (on-surface-variant) |
| `color: "rgba(255,255,255,0.25)"` | `color: "#b3b1b4"` (outline-variant) |
| `color: "#818CF8"` | `color: "#3557bc"` (primary) |
| `color: "#A78BFA"` | `color: "#274baf"` (primary-dim) |
| `background: "rgba(255,255,255,0.03)"` | `background: "#ffffff"` (card/surface-lowest) |
| `background: "rgba(255,255,255,0.04)"` | `background: "#f0edef"` (surface-container) |
| `background: "rgba(255,255,255,0.06)"` | `background: "#eae7ea"` (surface-container-high) |
| `border: "1px solid rgba(255,255,255,0.06)"` | `border: "1px solid #e4e2e5"` |
| `border: "1px solid rgba(255,255,255,0.08)"` | `border: "1px solid #b3b1b4"` |
| `background: "rgba(99,102,241,0.12)"` | `background: "#dce1ff"` (accent/primary-container) |
| `background: "linear-gradient(135deg, #6366F1, #A855F7)"` | `background: "#3557bc"` (solid primary) |
| `background: "rgba(10,10,15,0.92)"` | `background: "rgba(252,248,249,0.92)"` |
| `background: "rgba(239,68,68,0.1)"` | `background: "#ff8b9a33"` (error-container light) |
| `border: "1px solid rgba(239,68,68,0.2)"` | `border: "1px solid #9e3f4e33"` |
| `color: "#FCA5A5"` (error text) | `color: "#9e3f4e"` |
| `color: "#4ADE80"` (success) | `color: "#2e7d32"` (dark green for light bg) |
| `color: "#FBBF24"` (warning) | `color: "#b8860b"` (dark gold for light bg) |
| `color: "#60A5FA"` (info blue) | `color: "#3557bc"` |
| `background: "rgba(34,197,94,0.15)"` | `background: "#e8f5e9"` |
| `background: "rgba(245,158,11,0.15)"` | `background: "#fff3e0"` |
| `background: "rgba(59,130,246,0.15)"` | `background: "#e3f2fd"` |
| `background: "rgba(239,68,68,0.15)"` | `background: "#fce4ec"` |
| `hover:bg-white/5` | `hover:bg-black/5` |
| `hover:bg-white/[0.02]` | `hover:bg-black/[0.03]` |
| `hover:bg-white/[0.04]` | `hover:bg-black/[0.04]` |
| `hover:bg-white/[0.06]` | `hover:bg-black/[0.05]` |
| `text-white` (on cards/surfaces) | `text-foreground` or explicit `#323235` |
| `text-white/30` (placeholder) | `text-[#b3b1b4]` or `placeholder:text-muted-foreground/60` |
| `text-white/80` | `text-foreground/80` or `#323235cc` |
| `bg-black/60` (overlay) | `bg-black/40` |
| `"#1E1E2E"` (dropdown bg) | `"#ffffff"` with shadow |

### Status Badge Colors (light-mode friendly)
| Status | Old BG | New BG | Old Text | New Text |
|--------|--------|--------|----------|----------|
| Uploading/Info | `rgba(59,130,246,0.15)` | `#e3f2fd` | `#60A5FA` | `#1565c0` |
| Processing/Warning | `rgba(245,158,11,0.15)` | `#fff3e0` | `#FBBF24` | `#e65100` |
| Ready/Success | `rgba(34,197,94,0.15)` | `#e8f5e9` | `#4ADE80` | `#2e7d32` |
| Failed/Error | `rgba(239,68,68,0.15)` | `#fce4ec` | `#FCA5A5` | `#9e3f4e` |
| Expired/Cancelled | `rgba(255,255,255,0.06)` | `#f0edef` | `rgba(255,255,255,0.4)` | `#7b7a7d` |

### Shadow
| Usage | Value |
|-------|-------|
| Content card | `0 40px 40px -10px rgba(50,50,53,0.06)` |
| Dropdown/popover | `0 4px 24px rgba(50,50,53,0.12)` |

---

## Tasks

### Task 1: Update CSS Variables & Font Setup

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/layout.tsx`

**Step 1: Replace globals.css theme variables**

Replace `:root` and `.dark` blocks with Azure Ethos tokens. Add new surface-container custom properties for the tonal layering system.

```css
:root {
  --background: #fcf8f9;
  --foreground: #323235;
  --card: #ffffff;
  --card-foreground: #323235;
  --popover: #ffffff;
  --popover-foreground: #323235;
  --primary: #3557bc;
  --primary-foreground: #f8f7ff;
  --secondary: #e4e2e6;
  --secondary-foreground: #323235;
  --muted: #f0edef;
  --muted-foreground: #5f5f62;
  --accent: #dce1ff;
  --accent-foreground: #3557bc;
  --destructive: #9e3f4e;
  --border: #e4e2e5;
  --input: #b3b1b4;
  --ring: #3557bc;
  --chart-1: #3557bc;
  --chart-2: #625b77;
  --chart-3: #7190f8;
  --chart-4: #9e3f4e;
  --chart-5: #5f5f62;
  --radius: 0.5rem;
  --sidebar: #f6f3f4;
  --sidebar-foreground: #323235;
  --sidebar-primary: #3557bc;
  --sidebar-primary-foreground: #f8f7ff;
  --sidebar-accent: #dce1ff;
  --sidebar-accent-foreground: #3557bc;
  --sidebar-border: #e4e2e5;
  --sidebar-ring: #3557bc;

  /* Azure Ethos surface hierarchy */
  --surface: #fcf8f9;
  --surface-dim: #dcd9dd;
  --surface-bright: #fcf8f9;
  --surface-container-lowest: #ffffff;
  --surface-container-low: #f6f3f4;
  --surface-container: #f0edef;
  --surface-container-high: #eae7ea;
  --surface-container-highest: #e4e2e5;
  --on-surface: #323235;
  --on-surface-variant: #5f5f61;
  --outline: #7b7a7d;
  --outline-variant: #b3b1b4;
  --primary-container: #dce1ff;
  --primary-dim: #274baf;
  --tertiary: #625b77;
  --tertiary-container: #e8ddff;
  --error-container: #fce4ec;
}
```

Also add new Tailwind color mappings in `@theme inline`:

```css
--color-surface: var(--surface);
--color-surface-dim: var(--surface-dim);
--color-surface-container-lowest: var(--surface-container-lowest);
--color-surface-container-low: var(--surface-container-low);
--color-surface-container: var(--surface-container);
--color-surface-container-high: var(--surface-container-high);
--color-surface-container-highest: var(--surface-container-highest);
--color-on-surface: var(--on-surface);
--color-on-surface-variant: var(--on-surface-variant);
--color-outline: var(--outline);
--color-outline-variant: var(--outline-variant);
--color-primary-container: var(--primary-container);
--color-primary-dim: var(--primary-dim);
--color-tertiary: var(--tertiary);
--color-tertiary-container: var(--tertiary-container);
--color-error-container: var(--error-container);
```

**Step 2: Swap font from Inter to Plus Jakarta Sans**

In `layout.tsx`, replace the local Inter font with Plus Jakarta Sans from Google Fonts:

```tsx
import { Plus_Jakarta_Sans, JetBrains_Mono } from "next/font/google";

const plusJakarta = Plus_Jakarta_Sans({
  variable: "--font-plus-jakarta",
  subsets: ["latin"],
  display: "swap",
});
```

Update `globals.css`:
```css
--font-sans: var(--font-plus-jakarta), ui-sans-serif, system-ui, -apple-system, sans-serif;
```

**Step 3: Remove the `.dark` block** (we're light-mode only now) or keep it identical to `:root`.

**Step 4: Verify** — Run `pnpm dev` and confirm the app loads with the new light background.

**Step 5: Commit**
```bash
git add frontend/src/app/globals.css frontend/src/app/layout.tsx
git commit -m "feat(frontend): migrate CSS variables to Azure Ethos light theme with Plus Jakarta Sans"
```

---

### Task 2: Update Dashboard Layout & Sidebar

**Files:**
- Modify: `frontend/src/app/(dashboard)/layout.tsx`
- Modify: `frontend/src/components/layout/app-sidebar.tsx`

Update the dashboard layout background from `#0A0A0F` to `#fcf8f9`. Update the entire sidebar component — replace all hardcoded dark-theme inline styles with Azure Ethos equivalents using the mapping reference above.

Key changes in `app-sidebar.tsx`:
- Desktop sidebar: `background: "#f6f3f4"`, `borderRight: "1px solid #e4e2e5"`
- NavLink active: `background: "#dce1ff"`, `color: "#3557bc"`
- NavLink inactive: `color: "#5f5f62"`
- Section labels: `color: "#7b7a7d"`
- Logo gradient → solid `background: "#3557bc"`
- User avatar → solid `background: "#3557bc"`
- User name → `color: "#323235"` (remove `text-white`)
- User email → `color: "#5f5f62"`
- Mobile header → `background: "rgba(252,248,249,0.92)"`, `borderBottom: "1px solid #e4e2e5"`
- Mobile drawer → `background: "#fcf8f9"`, `borderRight: "1px solid #e4e2e5"`
- Hover states: `hover:bg-white/5` → `hover:bg-black/5`
- Footer border: `"1px solid #e4e2e5"`
- Logout icon: `color: "#7b7a7d"`

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/layout.tsx frontend/src/components/layout/app-sidebar.tsx
git commit -m "feat(frontend): update sidebar and dashboard layout to Azure Ethos"
```

---

### Task 3: Update Auth Pages

**Files:**
- Modify: `frontend/src/app/(auth)/layout.tsx`
- Modify: `frontend/src/app/(auth)/login/page.tsx`
- Modify: `frontend/src/app/(auth)/register/page.tsx`

Convert auth layout from dark to light:
- Background: `#fcf8f9`
- Brand panel: Keep a colored panel but use primary blue (`#3557bc`) as base or use `#f6f3f4` with blue accent orbs
- Gradient orbs: Use `#3557bc` and `#625b77` tinted orbs
- Text: Dark `#323235` on light backgrounds
- Form inputs: `background: "#f0edef"`, `border: "1px solid #b3b1b4"`, `color: "#323235"`, `placeholder:text-[#b3b1b4]`
- Submit button: `background: "#3557bc"` (solid, no gradient)
- Error alerts: `background: "#fce4ec"`, `border: "1px solid #9e3f4e33"`, `color: "#9e3f4e"`
- Links: `color: "#3557bc"`
- All `text-white` → `text-foreground` / `#323235`
- Focus ring: `focus:ring-[#3557bc]/50`

**Commit:**
```bash
git add frontend/src/app/\(auth\)/
git commit -m "feat(frontend): update auth pages to Azure Ethos light theme"
```

---

### Task 4: Update Dashboard Home Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/page.tsx`

- Title `text-white` → remove (use inherited foreground)
- Subtitle: `color: "#5f5f62"`
- Stat cards: `background: "#ffffff"`, `border: "1px solid #e4e2e5"`, add `boxShadow: "0 40px 40px -10px rgba(50,50,53,0.06)"`
- Stat icon backgrounds: Use `#dce1ff` (primary-container) for all, or keep distinct but lighter
- Stat values: `text-white` → `text-foreground`
- Quick action cards: Same card treatment
- Quick action icon gradients → solid primary `#3557bc`
- "Get started" link: `color: "#3557bc"`

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/page.tsx
git commit -m "feat(frontend): update dashboard page to Azure Ethos"
```

---

### Task 5: Update Chat Components

**Files:**
- Modify: `frontend/src/app/(dashboard)/chat/page.tsx`
- Modify: `frontend/src/components/chat/message-bubble.tsx`
- Modify: `frontend/src/components/chat/chat-input.tsx`
- Modify: `frontend/src/components/chat/conversation-list.tsx`

**chat/page.tsx:**
- Conversation sidebar: `background: "#f6f3f4"`, `borderRight: "1px solid #e4e2e5"`
- Mobile overlay: `bg-black/40`
- Chat header border: `"1px solid #e4e2e5"`
- Hamburger icon: `color: "#7b7a7d"`
- Title: remove `text-white`
- Empty state logo: `background: "#3557bc"`
- Title/subtitle: dark text on light
- Suggestion cards: `border: "1px solid #e4e2e5"`, `color: "#5f5f62"`, `hover:bg-black/[0.03]`
- Error banner: use Azure Ethos error palette

**message-bubble.tsx:**
- User bubble: `background: "#3557bc"`, `color: "#f8f7ff"`
- AI bubble: `background: "#f0edef"`, `color: "#323235"`
- AI avatar: `background: "#3557bc"`
- User avatar: `background: "#eae7ea"`
- Citation badge: `background: "#dce1ff"`, `color: "#3557bc"`
- Timestamp: `color: "#b3b1b4"`

**chat-input.tsx:**
- Input container: `background: "#f0edef"`, `border: "1px solid #e4e2e5"`
- Textarea: `color: "#323235"`, `placeholder: "#b3b1b4"`
- Send button: `background: "#3557bc"`
- Stop button: `background: "#fce4ec"`, `color: "#9e3f4e"`
- Model selector pill: `background: "#f0edef"`, `border: "1px solid #e4e2e5"`, `color: "#5f5f62"`
- Model dropdown: `background: "#ffffff"`, `border: "1px solid #e4e2e5"`, `boxShadow: "0 4px 24px rgba(50,50,53,0.12)"`

**conversation-list.tsx:**
- New Chat button: `background: "#3557bc"`
- Active conversation: `background: "#dce1ff"`, `color: "#3557bc"`
- Inactive: `color: "#5f5f62"`
- Message count: `color: "#7b7a7d"`
- Delete icon: `color: "#7b7a7d"`
- Border: `"1px solid #e4e2e5"`
- Empty state: `color: "#7b7a7d"`

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/chat/ frontend/src/components/chat/
git commit -m "feat(frontend): update chat components to Azure Ethos"
```

---

### Task 6: Update Documents Components

**Files:**
- Modify: `frontend/src/app/(dashboard)/documents/page.tsx`
- Modify: `frontend/src/components/documents/document-list.tsx`
- Modify: `frontend/src/components/documents/file-upload.tsx`
- Modify: `frontend/src/components/documents/drive-tree.tsx`

Apply the same pattern — replace all dark-theme inline styles using the mapping reference. Key changes:
- Page header: dark text
- Tab buttons: active `background: "#dce1ff"`, `color: "#3557bc"`, `border: "1px solid #3557bc33"` / inactive `background: "#f0edef"`, `color: "#5f5f62"`
- Upload area: dashed border `#b3b1b4`, hover/drag `#3557bc`, background `#f6f3f4`
- Document list cards: `background: "#ffffff"`, `border: "1px solid #e4e2e5"`
- File icon: `background: "#dce1ff"`, `color: "#3557bc"`
- Status badges: Use light-mode friendly status colors from reference
- Drive tree: Same card/surface treatment, folder icon `#b8860b`, file icon `#3557bc`

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/documents/ frontend/src/components/documents/
git commit -m "feat(frontend): update documents components to Azure Ethos"
```

---

### Task 7: Update Knowledge Graph Components

**Files:**
- Modify: `frontend/src/app/(dashboard)/knowledge/page.tsx`
- Modify: `frontend/src/components/knowledge/stats-card.tsx`
- Modify: `frontend/src/components/knowledge/graph-canvas.tsx` (just the color palette)

Same pattern for all inline styles. The graph canvas TYPE_COLORS should use darker, light-bg-friendly colors.

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/knowledge/ frontend/src/components/knowledge/
git commit -m "feat(frontend): update knowledge graph to Azure Ethos"
```

---

### Task 8: Update Settings Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/settings/page.tsx`

Largest single page — many sections. Apply the inline style mapping systematically:
- All card backgrounds: `#ffffff` with `border: "1px solid #e4e2e5"`
- Section icons: Use `#dce1ff`/`#3557bc` for profile, `#e8f5e9`/`#2e7d32` for models, `#e8ddff`/`#625b77` for preferences
- Input styles: `background: "#f0edef"`, `border: "1px solid #b3b1b4"`
- Select styles: Same as inputs
- Save buttons: `background: "#3557bc"` (profile), `background: "#2e7d32"` (models)
- Danger zone: `background: "#fce4ec"`, `border: "1px solid #9e3f4e33"`, `color: "#9e3f4e"`
- API key status badges: Configured = `background: "#e8f5e9"`, `color: "#2e7d32"` / Not configured = `background: "#f0edef"`, `color: "#7b7a7d"`
- Toggle switches: primary color `#3557bc` for active, `#b3b1b4` for inactive
- Cost card: Same card treatment

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/settings/
git commit -m "feat(frontend): update settings page to Azure Ethos"
```

---

### Task 9: Update Admin Ingestion Page

**Files:**
- Modify: `frontend/src/app/(dashboard)/admin/ingestion/page.tsx`

Apply the same pattern. Status badges need light-mode colors. Progress bars, job cards, cost card, worker summary — all follow the surface hierarchy and status badge reference.

**Commit:**
```bash
git add frontend/src/app/\(dashboard\)/admin/
git commit -m "feat(frontend): update admin ingestion to Azure Ethos"
```

---

### Task 10: Final Polish & Verification

- Run `pnpm dev` and visually check every page
- Grep for any remaining `#6366F1`, `#A855F7`, `#818CF8`, `#0A0A0F`, `rgba(255,255,255` references in `frontend/src/`
- Fix any missed hardcoded colors
- Test mobile views (drawer, header)
- Test graph canvas colors
- Verify all status badges are readable on light backgrounds

**Commit:**
```bash
git add -A
git commit -m "fix(frontend): clean up remaining dark-theme color references"
```
