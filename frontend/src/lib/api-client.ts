/**
 * Typed API client for the OpenRAG backend.
 *
 * All API calls go through this client. Never use fetch() directly
 * in components or hooks -- always use this client.
 */

import { getAccessToken } from "@/lib/token-store";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface ApiClientConfig {
  baseUrl: string;
  getToken?: () => string | null;
}

class ApiClient {
  private baseUrl: string;
  private getToken: () => string | null;
  /**
   * Called when a request receives a 401. Should attempt to refresh the
   * access token and return true if a new token is now available, or false
   * if the session cannot be recovered (triggers logout in the auth layer).
   */
  private onUnauthorized: (() => Promise<boolean>) | null = null;
  /** Guards against concurrent refresh attempts */
  private refreshPromise: Promise<boolean> | null = null;

  constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl;
    this.getToken = config.getToken || (() => null);
  }

  /**
   * If the response is a 401 and we haven't retried yet, attempt to refresh
   * the access token and invoke `retryFn` with the new credentials.
   */
  private async tryRefreshAndRetry<T>(
    response: Response,
    isRetry: boolean,
    retryFn: () => Promise<T>,
  ): Promise<{ response: Response; retried?: T }> {
    if (response.status === 401 && !isRetry && this.onUnauthorized) {
      if (!this.refreshPromise) {
        this.refreshPromise = this.onUnauthorized().finally(() => {
          this.refreshPromise = null;
        });
      }
      const refreshed = await this.refreshPromise;
      if (refreshed) {
        return { response, retried: await retryFn() };
      }
    }
    return { response };
  }

  /**
   * Register a callback that the client will invoke when any request
   * receives a 401. The callback should refresh the access token and
   * return true on success or false if the session is unrecoverable.
   *
   * Call this once from AuthProvider after it mounts.
   */
  setOnUnauthorized(handler: () => Promise<boolean>): void {
    this.onUnauthorized = handler;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    isRetry = false
  ): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    if (token) {
      (headers as Record<string, string>)["Authorization"] =
        `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    const { retried } = await this.tryRefreshAndRetry(response, isRetry, () =>
      this.request<T>(path, options, true),
    );
    if (retried !== undefined) return retried;

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: response.statusText,
      }));
      throw new ApiError(response.status, error.detail || "Unknown error");
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  async get<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "GET" });
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }

  /** Stream a POST request as Server-Sent Events.
   *
   * The backend sends standard SSE with separate `event:` and `data:` lines.
   * We parse these into `{ event, data }` objects for the callback.
   */
  async stream(
    path: string,
    body?: unknown,
    onEvent?: (event: { event: string; data: string }) => void,
    signal?: AbortSignal,
    isRetry = false,
  ): Promise<void> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });

    const { retried } = await this.tryRefreshAndRetry(response, isRetry, () =>
      this.stream(path, body, onEvent, signal, true),
    );
    if (retried !== undefined) return retried;

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: response.statusText,
      }));
      throw new ApiError(response.status, error.detail || "Unknown error");
    }

    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message"; // SSE default event type
    let dataChunks: string[] = []; // accumulate multi-line data: fields

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("event: ")) {
          currentEvent = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          dataChunks.push(line.slice(6));
        } else if (line === "") {
          // Empty line = end of SSE block — dispatch accumulated data
          if (dataChunks.length > 0) {
            const data = dataChunks.join("\n");
            dataChunks = [];
            if (data === "[DONE]") return;
            onEvent?.({ event: currentEvent, data });
          }
          currentEvent = "message";
        }
      }
    }
  }

  /** Upload a file with multipart/form-data */
  async upload<T>(path: string, formData: FormData, isRetry = false): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: formData,
    });

    const { retried } = await this.tryRefreshAndRetry(response, isRetry, () =>
      this.upload<T>(path, formData, true),
    );
    if (retried !== undefined) return retried;

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: response.statusText,
      }));
      throw new ApiError(response.status, error.detail || "Unknown error");
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const apiClient = new ApiClient({
  baseUrl: API_BASE_URL,
  getToken: () => getAccessToken(),
});
