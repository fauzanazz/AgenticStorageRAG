/** API response types -- mirrors backend Pydantic schemas */

export interface HealthResponse {
  status: string;
  version: string;
  environment: string;
}

/** Generic paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** Generic error response from the API */
export interface ApiErrorResponse {
  detail: string;
}
