export interface ApiKeyStatus {
  has_key: boolean;
}

export interface ClaudeSetupTokenStatus {
  has_token: boolean;
}

export interface ModelSettings {
  chat_model: string;
  ingestion_model: string;
  embedding_model: string;
  anthropic_api_key: ApiKeyStatus;
  openai_api_key: ApiKeyStatus;
  dashscope_api_key: ApiKeyStatus;
  openrouter_api_key: ApiKeyStatus;
  claude_setup_token: ClaudeSetupTokenStatus;
}

export interface UpdateModelSettingsRequest {
  chat_model?: string | null;
  ingestion_model?: string | null;
  embedding_model?: string | null;
  /** Empty string = unchanged, null = clear the key */
  anthropic_api_key?: string | null;
  openai_api_key?: string | null;
  dashscope_api_key?: string | null;
  openrouter_api_key?: string | null;
  claude_setup_token?: string | null;
}

export interface ModelOption {
  provider: string;
  model_id: string;
  label: string;
  supports_thinking?: boolean;
}

export interface ModelCatalog {
  chat_models: ModelOption[];
  embedding_models: ModelOption[];
}

export interface AvailableModelsResponse {
  models: ModelOption[];
  default_model: string | null;
}
