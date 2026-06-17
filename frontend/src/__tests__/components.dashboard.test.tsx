import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import DepositGoalCard from "@/components/dashboard/DepositGoalCard";
import GoalProgressCard from "@/components/dashboard/GoalProgressCard";
import DividendSection from "@/components/dashboard/DividendSection";

describe("DepositGoalCard", () => {
  it("goal이 없으면 설정 안내 메시지를 표시한다", () => {
    renderWithProviders(<DepositGoalCard goal={null} achievementPct={null} />);
    expect(screen.getByText("연간 입금 목표가 설정되지 않았습니다")).toBeInTheDocument();
  });

  it("achievementPct가 null이면 설정 안내 메시지를 표시한다", () => {
    renderWithProviders(<DepositGoalCard goal={10000000} achievementPct={null} />);
    expect(screen.getByText("연간 입금 목표가 설정되지 않았습니다")).toBeInTheDocument();
  });

  it("goal과 achievementPct가 있으면 달성률을 표시한다", () => {
    renderWithProviders(
      <DepositGoalCard goal={10000000} achievementPct={45.6} netDeposits={4560000} />,
    );
    expect(screen.getByText("45.6%")).toBeInTheDocument();
    expect(screen.getByText("달성")).toBeInTheDocument();
  });

  it("달성률이 100% 초과 시 100%로 클램핑된다", () => {
    renderWithProviders(
      <DepositGoalCard goal={10000000} achievementPct={120} netDeposits={12000000} />,
    );
    expect(screen.getByText("100.0%")).toBeInTheDocument();
  });

  it("netDeposits가 없으면 '—'를 표시한다", () => {
    renderWithProviders(<DepositGoalCard goal={10000000} achievementPct={30} netDeposits={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("올해 순입금액과 남은 금액 레이블을 표시한다", () => {
    renderWithProviders(
      <DepositGoalCard goal={10000000} achievementPct={50} netDeposits={5000000} />,
    );
    expect(screen.getByText("올해 순입금액")).toBeInTheDocument();
    expect(screen.getByText(/남음/)).toBeInTheDocument();
  });
});

describe("GoalProgressCard", () => {
  it("goal이 없으면 설정 안내 메시지를 표시한다", () => {
    renderWithProviders(<GoalProgressCard current={5000000} goal={null} pct={null} />);
    expect(screen.getByText("목표 금액이 설정되지 않았습니다")).toBeInTheDocument();
  });

  it("pct가 null이면 설정 안내 메시지를 표시한다", () => {
    renderWithProviders(<GoalProgressCard current={5000000} goal={10000000} pct={null} />);
    expect(screen.getByText("목표 금액이 설정되지 않았습니다")).toBeInTheDocument();
  });

  it("goal과 pct가 있으면 달성률을 표시한다", () => {
    renderWithProviders(<GoalProgressCard current={5000000} goal={10000000} pct={50} />);
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getByText("달성")).toBeInTheDocument();
  });

  it("달성률이 100% 초과 시 100%로 클램핑된다", () => {
    renderWithProviders(<GoalProgressCard current={15000000} goal={10000000} pct={150} />);
    expect(screen.getByText("100.0%")).toBeInTheDocument();
  });

  it("현재 자산과 목표 레이블을 표시한다", () => {
    renderWithProviders(<GoalProgressCard current={5000000} goal={10000000} pct={50} />);
    expect(screen.getByText("현재 자산")).toBeInTheDocument();
    expect(screen.getByText(/목표:/)).toBeInTheDocument();
    expect(screen.getByText(/남은 금액:/)).toBeInTheDocument();
  });
});

describe("DividendSection", () => {
  it("모든 배당 항목을 표시한다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={2.5}
      />,
    );
    expect(screen.getByText("연간 배당금")).toBeInTheDocument();
    expect(screen.getByText("실제 배당금")).toBeInTheDocument();
    expect(screen.getByText("월별 배당금")).toBeInTheDocument();
  });

  it("estimatedAnnual이 null이면 연간 배당금을 '—'로 표시한다", () => {
    renderWithProviders(
      <DividendSection annualReceived={null} estimatedAnnual={null} estimatedMonthly={null} />,
    );
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });

  it("estimatedAnnual > 0이면 수익률도 함께 표시한다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={2.5}
      />,
    );
    expect(screen.getByText("(2.50%)")).toBeInTheDocument();
  });

  it("overallDividendYield가 없으면 수익률을 표시하지 않는다", () => {
    renderWithProviders(
      <DividendSection
        annualReceived={500000}
        estimatedAnnual={600000}
        estimatedMonthly={50000}
        overallDividendYield={null}
      />,
    );
    expect(screen.queryByText(/%\)/)).toBeNull();
  });

  it("estimatedAnnual이 0이면 연간 배당금을 '—'로 표시한다", () => {
    renderWithProviders(
      <DividendSection annualReceived={0} estimatedAnnual={0} estimatedMonthly={0} />,
    );
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });
});
