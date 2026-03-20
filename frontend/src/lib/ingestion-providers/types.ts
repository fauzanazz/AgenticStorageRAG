import type { ComponentType } from "react";
import type { TriggerIngestionRequest } from "@/types/ingestion";

export interface FolderChooserProps {
  selectedFolderId: string | null;
  selectedFolderName: string | null;
  onSelect: (id: string, name: string) => void;
}

export interface ProviderState {
  folderId: string | null;
  folderName: string | null;
  setFolder: (id: string, name: string) => void;
  /** Whether the selected folder differs from the saved default */
  isDirty: boolean;
  saveDefault: () => Promise<void>;
  isSaving: boolean;
}

export interface IngestionProvider {
  key: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  hasFolderBrowser: boolean;
  FolderChooser: ComponentType<FolderChooserProps> | null;
  buildTriggerParams(state: {
    folderId: string | null;
    force: boolean;
  }): TriggerIngestionRequest;
  useProviderState(): ProviderState;
}
