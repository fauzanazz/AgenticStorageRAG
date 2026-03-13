/**
 * Tests for the auth hook's API response parsing.
 *
 * These tests exist because a contract mismatch between frontend and backend
 * once caused login to silently fail -- the frontend expected AuthTokens
 * directly, but the backend returned AuthResponse ({user, tokens}).
 *
 * The frontend tests had mocked away useAuth entirely, so the real parsing
 * logic was never exercised. These tests validate the actual response shape.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

// ---- Mock fetch globally ----

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// ---- Mock localStorage ----

const store: Record<string, string> = {};
const mockLocalStorage = {
  getItem: vi.fn((key: string) => store[key] ?? null),
  setItem: vi.fn((key: string, value: string) => {
    store[key] = value;
  }),
  removeItem: vi.fn((key: string) => {
    delete store[key];
  }),
};
vi.stubGlobal("localStorage", mockLocalStorage);

// ---- Import AFTER mocks ----

import { AuthProvider, useAuth } from "@/hooks/use-auth";

/** Backend AuthResponse shape -- the source of truth */
const MOCK_AUTH_RESPONSE = {
  user: {
    id: "550e8400-e29b-41d4-a716-446655440000",
    email: "test@example.com",
    full_name: "Test User",
    is_active: true,
    is_admin: false,
    created_at: "2026-01-01T00:00:00Z",
  },
  tokens: {
    access_token: "mock-access-token",
    refresh_token: "mock-refresh-token",
    token_type: "bearer",
    expires_in: 1800,
  },
};

/** Backend TokenResponse shape (used by /auth/refresh) */
const MOCK_TOKEN_RESPONSE = {
  access_token: "new-access-token",
  refresh_token: "new-refresh-token",
  token_type: "bearer",
  expires_in: 1800,
};

/** Backend UserResponse shape (used by /auth/me) */
const MOCK_USER_RESPONSE = {
  id: "550e8400-e29b-41d4-a716-446655440000",
  email: "test@example.com",
  full_name: "Test User",
  is_active: true,
  is_admin: false,
  created_at: "2026-01-01T00:00:00Z",
};

function createWrapper() {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <AuthProvider>{children}</AuthProvider>;
  };
}

function mockFetchResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

describe("useAuth - contract validation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.keys(store).forEach((key) => delete store[key]);

    // Default: no stored token, so useEffect won't call /auth/me
    mockLocalStorage.getItem.mockImplementation((key: string) => store[key] ?? null);
    mockLocalStorage.setItem.mockImplementation((key: string, value: string) => {
      store[key] = value;
    });
    mockLocalStorage.removeItem.mockImplementation((key: string) => {
      delete store[key];
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("login correctly parses AuthResponse with nested {user, tokens}", async () => {
    // Backend returns AuthResponse: { user: {...}, tokens: {...} }
    mockFetch.mockResolvedValueOnce(
      mockFetchResponse(200, MOCK_AUTH_RESPONSE)
    );

    const { result } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    // Wait for initial loading to complete
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Perform login
    await act(async () => {
      await result.current.login("test@example.com", "password123");
    });

    // Verify tokens were stored correctly
    expect(store["access_token"]).toBe("mock-access-token");
    expect(store["refresh_token"]).toBe("mock-refresh-token");

    // Verify user state was set from the response
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user).toEqual(
      expect.objectContaining({
        email: "test@example.com",
        full_name: "Test User",
      })
    );
  });

  it("register correctly parses AuthResponse with nested {user, tokens}", async () => {
    mockFetch.mockResolvedValueOnce(
      mockFetchResponse(200, MOCK_AUTH_RESPONSE)
    );

    const { result } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.register(
        "test@example.com",
        "password123",
        "Test User"
      );
    });

    expect(store["access_token"]).toBe("mock-access-token");
    expect(store["refresh_token"]).toBe("mock-refresh-token");
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.user?.full_name).toBe("Test User");
  });

  it("login would fail if backend returned flat TokenResponse (regression guard)", async () => {
    // Simulate the OLD bug: backend returns {access_token, ...} without nesting
    const FLAT_TOKEN_RESPONSE = {
      access_token: "flat-access",
      refresh_token: "flat-refresh",
      token_type: "bearer",
      expires_in: 1800,
    };

    mockFetch.mockResolvedValueOnce(
      mockFetchResponse(200, FLAT_TOKEN_RESPONSE)
    );

    const { result } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Login should throw or fail because response.tokens is undefined
    // when the backend returns a flat structure instead of nested
    await act(async () => {
      try {
        await result.current.login("test@example.com", "password123");
      } catch {
        // Expected -- response.tokens would be undefined
      }
    });

    // Tokens should NOT be stored (response.tokens was undefined)
    // This catches the exact bug we had
    expect(store["access_token"]).toBeUndefined();
  });

  it("refresh correctly parses flat TokenResponse then fetches user", async () => {
    // Set up: user has a stored refresh token
    store["refresh_token"] = "existing-refresh-token";

    // Mock: first call is /auth/refresh (returns TokenResponse),
    // second call is /auth/me (returns UserResponse)
    mockFetch
      .mockResolvedValueOnce(mockFetchResponse(200, MOCK_TOKEN_RESPONSE))
      .mockResolvedValueOnce(mockFetchResponse(200, MOCK_USER_RESPONSE));

    const { result } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    // Wait for initial load (will call /auth/me, may trigger refresh)
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Manually trigger refresh
    await act(async () => {
      await result.current.refreshAuth();
    });

    // Verify new tokens stored
    expect(store["access_token"]).toBe("new-access-token");
    expect(store["refresh_token"]).toBe("new-refresh-token");
  });

  it("logout clears tokens and resets state", async () => {
    // Start authenticated
    mockFetch.mockResolvedValueOnce(
      mockFetchResponse(200, MOCK_AUTH_RESPONSE)
    );

    const { result } = renderHook(() => useAuth(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Login first
    await act(async () => {
      await result.current.login("test@example.com", "password123");
    });
    expect(result.current.isAuthenticated).toBe(true);

    // Logout
    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeNull();
    expect(store["access_token"]).toBeUndefined();
    expect(store["refresh_token"]).toBeUndefined();
  });
});
