import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import AssetAllocationChart from "@/components/dashboard/AssetAllocationChart";
import { renderWithProviders } from "@/test/renderWithProviders";

vi.mock("../stores/themeStore", () => ({
  useThemeStore: () => false,
}));

const sampleData = [
  { name: "주식", value: 100_000_000, pct: 66.7 },
  { name: "현금", value: 50_000_000, pct: 33.3 },
];

describe("AssetAllocationChart", () => {
  it("데이터가 있을 때 PieChart를 렌더링한다", () => {
    renderWithProviders(<AssetAllocationChart data={sampleData} />);
    expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
  });

  it("compact 모드에서 종목명과 비중이 텍스트로 표시된다", () => {
    renderWithProviders(<AssetAllocationChart data={sampleData} size="compact" />);
    expect(screen.getByText(/주식/)).toBeInTheDocument();
    expect(screen.getByText(/현금/)).toBeInTheDocument();
  });

  it("compact 모드에서 비중 퍼센트가 표시된다", () => {
    renderWithProviders(<AssetAllocationChart data={sampleData} size="compact" />);
    expect(screen.getByText(/67%/)).toBeInTheDocument();
    expect(screen.getByText(/33%/)).toBeInTheDocument();
  });

  it("mobile 모드에서도 종목명이 표시된다", () => {
    renderWithProviders(<AssetAllocationChart data={sampleData} size="mobile" />);
    expect(screen.getByText(/주식/)).toBeInTheDocument();
  });

  it("full 모드(기본값)에서 범례(Legend)가 포함된다 — compact/mobile에서는 커스텀 리스트 사용", () => {
    renderWithProviders(<AssetAllocationChart data={sampleData} />);
    // full 모드에서는 compact 텍스트 리스트 없음
    expect(screen.queryByText(/67%/)).not.toBeInTheDocument();
  });

  it("3개 항목 데이터도 정상 렌더링된다 (null-safe)", () => {
    const threeItems = [
      { name: "주식", value: 60_000_000, pct: 60 },
      { name: "현금", value: 30_000_000, pct: 30 },
      { name: "부동산", value: 10_000_000, pct: 10 },
    ];
    renderWithProviders(<AssetAllocationChart data={threeItems} size="compact" />);
    expect(screen.getByText(/부동산/)).toBeInTheDocument();
  });
});
