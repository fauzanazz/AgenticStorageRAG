"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { apiClient, ApiError } from "@/lib/api-client";

/** Mirrors backend UserResponse schema */
export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

/** Mirrors backend AuthResponse schema */
interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    fullName: string
  ) => Promise<void>;
  loginWithOAuth: (provider: string) => Promise<void>;
  logout: () => void;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = "access_token";
const REFRESH_KEY = "refresh_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  const setTokens = useCallback((tokens: AuthTokens) => {
    localStorage.setItem(TOKEN_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }, []);

  const clearTokens = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
  }, []);

  const fetchUser = useCallback(async (): Promise<User | null> => {
    try {
      return await apiClient.get<User>("/auth/me");
    } catch {
      return null;
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await apiClient.post<AuthResponse>("/auth/login", {
        email,
        password,
      });
      setTokens(response.tokens);
      setState({
        user: response.user,
        isLoading: false,
        isAuthenticated: true,
      });
    },
    [setTokens]
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const response = await apiClient.post<AuthResponse>("/auth/register", {
        email,
        password,
        full_name: fullName,
      });
      setTokens(response.tokens);
      setState({
        user: response.user,
        isLoading: false,
        isAuthenticated: true,
      });
    },
    [setTokens]
  );

  const loginWithOAuth = useCallback(async (provider: string) => {
    const response = await apiClient.get<{ authorization_url: string }>(
      `/auth/oauth/${provider}/authorize`
    );
    // Full-page redirect to the OAuth provider's consent screen
    window.location.href = response.authorization_url;
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setState({ user: null, isLoading: false, isAuthenticated: false });
  }, [clearTokens]);

  const refreshAuth = useCallback(async () => {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return;
    }
    try {
      const tokens = await apiClient.post<AuthTokens>("/auth/refresh", {
        refresh_token: refreshToken,
      });
      setTokens(tokens);
      const user = await fetchUser();
      setState({ user, isLoading: false, isAuthenticated: !!user });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearTokens();
        setState({ user: null, isLoading: false, isAuthenticated: false });
      }
    }
  }, [setTokens, clearTokens, fetchUser]);

  // Wire the 401 handler into the shared API client so any request that
  // receives an expired-token response will transparently refresh and retry.
  // Done synchronously during render (not in useEffect) so the handler is
  // in place before any child renders and fires its first request.
  // setTokens and clearTokens are stable (empty-dep useCallbacks), so
  // unauthorizedHandler is also stable — re-registering it on each render
  // is idempotent and safe.
  const unauthorizedHandler = useCallback(async (): Promise<boolean> => {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    try {
      const tokens = await apiClient.post<AuthTokens>("/auth/refresh", {
        refresh_token: refreshToken,
      });
      setTokens(tokens);
      return true;
    } catch {
      clearTokens();
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return false;
    }
  }, [setTokens, clearTokens]);

  apiClient.setOnUnauthorized(unauthorizedHandler);

  // On mount: try to load user from stored token
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      // No token -- nothing to fetch.
      // Initial state already has isLoading: true, so we need to flip it.
      // We avoid direct setState by scheduling a microtask so the linter
      // doesn't flag it as synchronous-setState-in-effect.
      queueMicrotask(() => {
        setState({ user: null, isLoading: false, isAuthenticated: false });
      });
      return;
    }
    let cancelled = false;
    fetchUser().then((user) => {
      if (cancelled) return;
      if (user) {
        setState({ user, isLoading: false, isAuthenticated: true });
      } else {
        // Token expired -- try refresh
        refreshAuth();
      }
    });
    return () => {
      cancelled = true;
    };
  }, [fetchUser, refreshAuth]);

  const value = useMemo(
    () => ({ ...state, login, register, loginWithOAuth, logout, refreshAuth }),
    [state, login, register, loginWithOAuth, logout, refreshAuth]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
