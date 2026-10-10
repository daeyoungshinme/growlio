import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, render } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([
    { id: "a1", name: "KIS 일반", asset_type: "STOCK_KIS" },
    { id: "a2", name: "키움 ISA", asset_type: "STOCK_KIWOOM" },
  ]),
}));
vi.mock("@/components/portfolio-analysis/TaxLimitsSection", () => ({
  default: () => <div data-testid="tax-limits-section" />,
}));
vi.mock("@/components/portfolio-analysis/TaxOptimizationCard", () => ({
  default: ({ accountId }: { accountId?: string | null }) => (
    <div data-testid="tax-optimization">{accountId ?? "all"}</div>
  ),
}));

import TaxTabContainer from "@/components/portfolio-analysis/TaxTabContainer";
import AssetsPage from "@/pages/AssetsPage";

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{decodeURIComponent(loc.pathname + loc.search)}</div>;
}

function renderAt(initial: string, element: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/assets" element={element} />
          <Route
            path="/invest-plan"
            element={
              <>
                <TaxTabContainer />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TaxTabContainer (계획 › 절세)", () => {
  it("옛 자산 세금 링크로 들어오면 계획 › 절세로 이동한다", async () => {
    renderAt("/assets?tab=투자현황&portfolioTab=세금", <AssetsPage />);
    expect(await screen.findByTestId("tax-limits-section")).toBeInTheDocument();
    expect(screen.getByTestId("location").textContent).toBe("/invest-plan?tab=절세");
  });

  it("기본은 한도 현황, 세금 추정 탭에서 계좌를 고르면 그 계좌로 조회한다", async () => {
    renderAt("/invest-plan?tab=절세", null);
    expect(screen.getByTestId("tax-limits-section")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "세금 추정" }));
    expect(screen.getByTestId("tax-optimization").textContent).toBe("all");

    const select = await screen.findByLabelText("세금 추정 계좌 선택");
    fireEvent.change(select, { target: { value: "a2" } });
    expect(screen.getByTestId("tax-optimization").textContent).toBe("a2");
    expect(screen.getByTestId("location").textContent).toContain("taxAccount=a2");
  });
});
