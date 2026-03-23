/**
 * In-memory access token store.
 *
 * Keeps the short-lived access token out of localStorage to limit XSS impact.
 * The token is lost on page reload — the auth layer refreshes it automatically.
 *
 * TODO: The refresh token is stored in localStorage, which is vulnerable to XSS.
 * A more secure approach would be to store it in an httpOnly cookie via a BFF pattern.
 * See: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
 */

let accessToken: string | null = null;

/** localStorage key for the refresh token. */
export const REFRESH_TOKEN_KEY = "refresh_token";

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
