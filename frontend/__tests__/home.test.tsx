import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import Page from "@/app/page";

describe("Home Page", () => {
  it("renders without crashing", () => {
    render(<Page />);
    // The default Next.js page should render some content
    expect(document.body).toBeTruthy();
  });
});
