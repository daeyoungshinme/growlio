import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import { api } from "@/api/client";
import {
  fetchPortfolioOverview,
  fetchPortfolioOverviewLite,
  fetchAllocationHistory,
  fetchPortfolios,
  createPortfolio,
  updatePortfolio,
  deletePortfolio,
  reorderPortfolios,
} from "@/api/portfolios";

const mockPortfolio = {
  id: "port-1",
  name: "성장형",
  items: [{ ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 50 }],
  base_type: "STOCK_ONLY",
  sort_order: 0,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("api/portfolios", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchPortfolioOverview calls GET /portfolio/overview", async () => {
    const mockOverview = { total_invested_krw: 0 };
    vi.mocked(api.get).mockResolvedValue({ data: mockOverview });
    const result = await fetchPortfolioOverview();
    expect(api.get).toHaveBeenCalledWith("/portfolio/overview");
    expect(result).toEqual(mockOverview);
  });

  it("fetchPortfolioOverviewLite calls GET /portfolio/overview with lite param", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchPortfolioOverviewLite();
    expect(api.get).toHaveBeenCalledWith("/portfolio/overview", { params: { lite: true } });
  });

  it("fetchAllocationHistory calls GET /portfolio/allocation-history", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchAllocationHistory(12);
    expect(api.get).toHaveBeenCalledWith("/portfolio/allocation-history", {
      params: { months: 12 },
    });
  });

  it("fetchPortfolios calls GET /portfolios", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockPortfolio] });
    const result = await fetchPortfolios();
    expect(api.get).toHaveBeenCalledWith("/portfolios");
    expect(result).toEqual([mockPortfolio]);
  });

  it("createPortfolio calls POST /portfolios", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockPortfolio });
    const body = { name: "성장형", items: [{ ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 100 }] };
    const result = await createPortfolio(body);
    expect(api.post).toHaveBeenCalledWith("/portfolios", body);
    expect(result).toEqual(mockPortfolio);
  });

  it("updatePortfolio calls PUT /portfolios/:id", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: mockPortfolio });
    const result = await updatePortfolio("port-1", { name: "업데이트" });
    expect(api.put).toHaveBeenCalledWith("/portfolios/port-1", { name: "업데이트" });
    expect(result).toEqual(mockPortfolio);
  });

  it("deletePortfolio calls DELETE /portfolios/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({});
    await deletePortfolio("port-1");
    expect(api.delete).toHaveBeenCalledWith("/portfolios/port-1");
  });

  it("reorderPortfolios calls PATCH /portfolios/reorder", async () => {
    vi.mocked(api.patch).mockResolvedValue({});
    const items = [{ id: "port-1", sort_order: 0 }];
    await reorderPortfolios(items);
    expect(api.patch).toHaveBeenCalledWith("/portfolios/reorder", { items });
  });
});
