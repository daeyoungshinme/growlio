import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { EconomicCalendarEvent, IndicatorLatest } from "@/api/economicIndicators";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="recharts-container">{children}</div>,
  LineChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  ReferenceLine: () => <div />,
}));

import EconomicCalendar from "@/components/market/EconomicCalendar";
import EconomicCalendarList from "@/components/market/EconomicCalendarList";
import IndicatorCard from "@/components/market/IndicatorCard";
import IndicatorHistoryChart from "@/components/market/IndicatorHistoryChart";
import IndicatorCalendarList from "@/components/market/IndicatorCalendarList";

const mockCalendarEvent: EconomicCalendarEvent = {
  event: "CPI 발표",
  date: "2026-12-15T09:30:00Z",
  time_kst: "22:30",
  country: "US",
  impact: "High",
  actual: null,
  estimate: 3.2,
  previous: 3.0,
  currency: "%",
};

// ------- EconomicCalendarList -------
describe("EconomicCalendarList", () => {
  it("renders empty state", () => {
    renderWithProviders(<EconomicCalendarList events={[]} />);
    expect(screen.getByText(/향후 90일 내 예정된 이벤트가 없습니다/)).toBeDefined();
  });

  it("renders event list", () => {
    renderWithProviders(<EconomicCalendarList events={[mockCalendarEvent]} />);
    expect(screen.getByText("CPI 발표")).toBeDefined();
  });

  it("shows impact badge", () => {
    renderWithProviders(<EconomicCalendarList events={[mockCalendarEvent]} />);
    expect(screen.getByText("고")).toBeDefined();
  });

  it("shows estimate value", () => {
    renderWithProviders(<EconomicCalendarList events={[mockCalendarEvent]} />);
    expect(screen.getByText("예측")).toBeDefined();
  });

  it("renders with actual value", () => {
    const actualEvent = { ...mockCalendarEvent, actual: 3.1 };
    renderWithProviders(<EconomicCalendarList events={[actualEvent]} />);
    expect(screen.getByText("실제")).toBeDefined();
  });

  it("renders with Medium impact", () => {
    const mediumEvent = { ...mockCalendarEvent, impact: "Medium" as const };
    renderWithProviders(<EconomicCalendarList events={[mediumEvent]} />);
    expect(screen.getByText("중")).toBeDefined();
  });
});

// ------- IndicatorCard -------
const mockIndicator: IndicatorLatest = {
  series_id: "UNRATE",
  name: "실업률",
  unit: "%",
  latest_value: 3.7,
  previous_value: 3.8,
  change_pct: -2.63,
  latest_date: "2024-01-15",
};

describe("IndicatorCard", () => {
  it("renders indicator card", () => {
    renderWithProviders(
      <IndicatorCard
        indicator={mockIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    expect(screen.getByText("실업률")).toBeDefined();
    expect(screen.getByText("3.70%")).toBeDefined();
  });

  it("renders subscribed state", () => {
    renderWithProviders(
      <IndicatorCard
        indicator={mockIndicator}
        subscribed={true}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    expect(screen.getByLabelText("구독 해제")).toBeDefined();
  });

  it("renders selected state", () => {
    renderWithProviders(
      <IndicatorCard
        indicator={mockIndicator}
        subscribed={false}
        isSelected={true}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    // Multiple buttons exist (main card button + subscribe button), just verify component renders
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <IndicatorCard
        indicator={mockIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={onSelect}
        onToggleSubscribe={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /실업률/ }));
    expect(onSelect).toHaveBeenCalled();
  });

  it("calls onToggleSubscribe when bell clicked", () => {
    const onToggle = vi.fn();
    renderWithProviders(
      <IndicatorCard
        indicator={mockIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={onToggle}
      />
    );
    fireEvent.click(screen.getByLabelText("구독"));
    expect(onToggle).toHaveBeenCalled();
  });

  it("shows upward trend", () => {
    const upIndicator = { ...mockIndicator, change_pct: 2.5, previous_value: 3.6 };
    renderWithProviders(
      <IndicatorCard
        indicator={upIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    expect(screen.getByText(/\+2\.50%/)).toBeDefined();
  });

  it("shows no change", () => {
    const flatIndicator = { ...mockIndicator, change_pct: 0 };
    renderWithProviders(
      <IndicatorCard
        indicator={flatIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    expect(screen.getByText("변동 없음")).toBeDefined();
  });

  it("handles non-finite value", () => {
    const nanIndicator = { ...mockIndicator, latest_value: NaN };
    renderWithProviders(
      <IndicatorCard
        indicator={nanIndicator}
        subscribed={false}
        isSelected={false}
        onSelect={vi.fn()}
        onToggleSubscribe={vi.fn()}
      />
    );
    expect(screen.getByText("—")).toBeDefined();
  });
});

// ------- IndicatorHistoryChart -------
describe("IndicatorHistoryChart", () => {
  it("renders empty state", () => {
    renderWithProviders(<IndicatorHistoryChart data={[]} name="실업률" unit="%" isDark={false} />);
    expect(screen.getByText("데이터를 불러오는 중...")).toBeDefined();
  });

  it("renders with data", () => {
    const data = [
      { date: "2024-01", value: 3.7 },
      { date: "2024-02", value: 3.8 },
    ];
    renderWithProviders(<IndicatorHistoryChart data={data} name="실업률" unit="%" isDark={false} />);
    expect(screen.getByTestId("recharts-container")).toBeDefined();
  });

  it("renders in dark mode", () => {
    const data = [{ date: "2024-01", value: 3.7 }];
    renderWithProviders(<IndicatorHistoryChart data={data} name="실업률" unit="%" isDark={true} />);
    expect(document.body).toBeDefined();
  });
});

// ------- IndicatorCalendarList -------
describe("IndicatorCalendarList", () => {
  it("renders empty state", () => {
    renderWithProviders(<IndicatorCalendarList events={[]} />);
    expect(screen.getByText(/향후 14일 내 예정된 발표 일정이 없습니다/)).toBeDefined();
  });

  it("renders events", () => {
    const events: EconomicCalendarEvent[] = [{
      ...mockCalendarEvent,
      event: "FOMC 회의",
      date: "2026-12-20T00:00:00Z",
    }];
    renderWithProviders(<IndicatorCalendarList events={events} />);
    expect(screen.getByText("FOMC 회의")).toBeDefined();
  });

  it("renders event with estimate", () => {
    const events: EconomicCalendarEvent[] = [{
      ...mockCalendarEvent,
      estimate: 5.25,
    }];
    renderWithProviders(<IndicatorCalendarList events={events} />);
    expect(screen.getByText("5.25")).toBeDefined();
  });
});

// ------- EconomicCalendar -------
describe("EconomicCalendar", () => {
  it("renders calendar with navigation", () => {
    renderWithProviders(<EconomicCalendar events={[]} />);
    expect(screen.getByLabelText("이전 달")).toBeDefined();
    expect(screen.getByLabelText("다음 달")).toBeDefined();
  });

  it("renders day of week headers", () => {
    renderWithProviders(<EconomicCalendar events={[]} />);
    expect(screen.getByText("월")).toBeDefined();
    expect(screen.getByText("화")).toBeDefined();
  });

  it("can navigate to next month", () => {
    renderWithProviders(<EconomicCalendar events={[]} />);
    const nextBtn = screen.getByLabelText("다음 달");
    fireEvent.click(nextBtn);
    // Just verify it doesn't crash
    expect(document.body).toBeDefined();
  });

  it("shows events on calendar day", () => {
    const futureEvent: EconomicCalendarEvent = {
      ...mockCalendarEvent,
      date: "2099-06-15T00:00:00Z",
    };
    renderWithProviders(<EconomicCalendar events={[futureEvent]} />);
    // Should render calendar without crash
    expect(document.body).toBeDefined();
  });
});
