import type { IngestionProvider } from "./types";

const _registry = new Map<string, IngestionProvider>();

export function registerProvider(provider: IngestionProvider): void {
  _registry.set(provider.key, provider);
}

export function getProvider(key: string): IngestionProvider | undefined {
  return _registry.get(key);
}

export function getAllProviders(): IngestionProvider[] {
  return Array.from(_registry.values());
}
