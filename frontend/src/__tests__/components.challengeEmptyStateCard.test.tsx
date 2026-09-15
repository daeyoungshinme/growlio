import { describe, it, expect, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { renderWithProviders } from "@/test/renderWithProviders";
import ChallengeEmptyStateCard from "@/components/dashboard/ChallengeEmptyStateCard";

function render() {
  return renderWithProviders(
    <MemoryRouter>
      <ChallengeEmptyStateCard />
    </MemoryRouter>,
  );
}

describe("ChallengeEmptyStateCard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows a CTA linking to the challenge tab", () => {
    render();
    expect(screen.getByText("적립 습관을 챌린지로 만들어보세요")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/invest-plan?tab=챌린지");
  });

  it("hides itself and persists dismissal after clicking close", () => {
    const { container, unmount } = render();
    fireEvent.click(screen.getByLabelText("카드 닫기"));
    expect(container).toBeEmptyDOMElement();
    unmount();

    const { container: reRendered } = render();
    expect(reRendered).toBeEmptyDOMElement();
  });
});
