export interface ApiKeyStatus {
  has_key: boolean;
}

export interface ModelSettings {
  chat_model: string;
  ingestion_model: string;
  embedding_model: string;
  anthropic_api_key: ApiKeyStatus;
  openai_api_key: ApiKeyStatus;
  dashscope_api_key: ApiKeyStatus;
}

export interface UpdateModelSettingsRequest {
  chat_model?: string | null;
  ingestion_model?: string | null;
  embedding_model?: string | null;
  /** Empty string = unchanged, null = clear the key */
  anthropic_api_key?: string | null;
  openai_api_key?: string | null;
  dashscope_api_key?: string | null;
}

export interface ModelOption {
  provider: string;
  model_id: string;
  label: string;
}

export interface ModelCatalog {
  chat_models: ModelOption[];
  embedding_models: ModelOption[];
}
