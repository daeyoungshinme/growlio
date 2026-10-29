import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import MiniDonut from "@/components/common/MiniDonut";

const data = [
  { name: "주식", value: 600, pct: 60 },
  { name: "예금", value: 400, pct: 40 },
];

describe("MiniDonut", () => {
  it("조각별 원호와 접근성 요약을 그린다", () => {
    const { container } = render(<MiniDonut data={data} />);
    expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
      "자산 구성: 주식 60%, 예금 40%",
    );
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("조각을 누르면 가운데에 이름·비중을 보여주고 다시 누르면 숨긴다", () => {
    const { container } = render(<MiniDonut data={data} />);
    const first = container.querySelectorAll("circle")[0];
    fireEvent.click(first!);
    expect(screen.getByText("60.0%")).toBeDefined();
    fireEvent.click(first!);
    expect(screen.queryByText("60.0%")).toBeNull();
  });

  it("합계가 0이면 아무것도 그리지 않는다", () => {
    const { container } = render(<MiniDonut data={[{ name: "x", value: 0, pct: 0 }]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});
