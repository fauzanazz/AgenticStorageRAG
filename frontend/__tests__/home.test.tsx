import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/",
}));

// Mock the auth hook
const mockAuth = {
  user: { id: "1", email: "test@test.com", full_name: "Test User", is_active: true, created_at: "" },
  isLoading: false,
  isAuthenticated: true,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshAuth: vi.fn(),
};

vi.mock("@/hooks/use-auth", () => ({
  useAuth: () => mockAuth,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock sidebar components that require SidebarProvider context
vi.mock("@/components/layout/mobile-header", () => ({
  MobileHeader: ({ title }: { title?: string }) => (
    <header data-testid="mobile-header">{title || "DriveRAG"}</header>
  ),
}));

import DashboardPage from "@/app/(dashboard)/page";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders welcome message with user name", () => {
    const Wrapper = createWrapper();
    render(<Wrapper><DashboardPage /></Wrapper>);
    expect(screen.getByText(/Welcome back, Test User/)).toBeTruthy();
  });

  it("renders quick action cards", () => {
    const Wrapper = createWrapper();
    render(<Wrapper><DashboardPage /></Wrapper>);
    expect(screen.getByText("Upload Document")).toBeTruthy();
    expect(screen.getByText("Start Chat")).toBeTruthy();
    expect(screen.getByText("Knowledge Graph")).toBeTruthy();
  });

  it("renders stats placeholders", () => {
    const Wrapper = createWrapper();
    render(<Wrapper><DashboardPage /></Wrapper>);
    // Stats section has both label + value -- use getAllByText for "Documents" since
    // it also appears in the quick actions section
    expect(screen.getAllByText("Documents").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Knowledge Nodes")).toBeTruthy();
    expect(screen.getByText("Chunks")).toBeTruthy();
    expect(screen.getByText("Embeddings")).toBeTruthy();
    // Check placeholder values (4 stat cards with "--" when no data)
    expect(screen.getAllByText("--").length).toBe(4);
  });
});
