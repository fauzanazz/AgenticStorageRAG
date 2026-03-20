/**
 * In-memory access token store.
 *
 * Keeps the short-lived access token out of localStorage to limit XSS impact.
 * The token is lost on page reload — the auth layer refreshes it automatically.
 */

let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
