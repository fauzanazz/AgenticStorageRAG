# ============================================================
# Frontend Dockerfile
# Stages: deps → development | builder → production
#
# Layer-cache strategy:
#   1. Copy only package.json + package-lock.json → npm ci
#      (this layer is only busted when deps change)
#   2. Copy source code last
#      (source changes never re-trigger npm ci)
# ============================================================

# ---- Stage 1: install dependencies -------------------------
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# ---- Stage 2: development ----------------------------------
FROM node:22-alpine AS development

WORKDIR /app

# Seed node_modules from the deps stage.
# The docker-compose anonymous volume at /app/node_modules overlays this
# at runtime, but docker-entrypoint.sh runs `npm install` on every start
# to keep the volume in sync when package.json has changed since the
# volume was last created.
COPY --from=deps /app/node_modules ./node_modules

# Copy source last: source changes bust only this layer.
COPY . .

# Entrypoint runs `npm install` before handing off to CMD so that a
# stale anonymous volume is always healed without a full image rebuild.
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["npx", "next", "dev", "--webpack"]

# ---- Stage 3: builder (production build) -------------------
FROM deps AS builder

COPY . .
RUN npm run build

# ---- Stage 4: production -----------------------------------
FROM node:22-alpine AS production

WORKDIR /app

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

ENV PORT=3000
CMD ["node", "server.js"]
