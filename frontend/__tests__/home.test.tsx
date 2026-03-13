import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

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
    <header data-testid="mobile-header">{title || "DingDong RAG"}</header>
  ),
}));

import DashboardPage from "@/app/(dashboard)/page";

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders welcome message with user name", () => {
    render(<DashboardPage />);
    expect(screen.getByText(/Welcome back, Test User/)).toBeTruthy();
  });

  it("renders quick action cards", () => {
    render(<DashboardPage />);
    expect(screen.getByText("Upload Document")).toBeTruthy();
    expect(screen.getByText("Chat")).toBeTruthy();
    expect(screen.getByText("Knowledge Graph")).toBeTruthy();
  });

  it("renders stats placeholders", () => {
    render(<DashboardPage />);
    // Stats section has both label + value -- use getAllByText for "Documents" since
    // it also appears in the quick actions section
    expect(screen.getAllByText("Documents").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Knowledge Nodes")).toBeTruthy();
    expect(screen.getByText("Chat Sessions")).toBeTruthy();
    // Check placeholder values
    expect(screen.getAllByText("--").length).toBe(3);
  });
});
