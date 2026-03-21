export type { IngestionProvider, FolderChooserProps, ProviderState } from "./types";
export { getProvider, getAllProviders } from "./registry";

// Auto-register built-in providers
import { googleDriveProvider } from "./google-drive";
import { registerProvider } from "./registry";

registerProvider(googleDriveProvider);
