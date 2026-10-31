import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { PortfolioItem } from "@/api/portfolios";
import PortfolioGroupItemRow from "../PortfolioGroupItemRow";

function makeItem(overrides: Partial<PortfolioItem> = {}): PortfolioItem {
  return {
    ticker: "QQQ",
    name: "Invesco QQQ",
    market: "NASDAQ",
    weight: 40,
    group: {
      key: "NASDAQ100",
      label: "나스닥 100",
      members: [
        { ticker: "QQQM", market: "NASDAQ", name: "Invesco QQQM" },
        { ticker: "QLD", market: "AMEX", name: "ProShares QLD", leverage: 2 },
      ],
      domestic_alt: { ticker: "133690", market: "KOSPI", name: "TIGER 미국나스닥100" },
    },
    ...overrides,
  };
}

function renderRow(item = makeItem()) {
  const onChange = vi.fn();
  const onRemove = vi.fn();
  render(<PortfolioGroupItemRow item={item} idx={2} onChange={onChange} onRemove={onRemove} />);
  return { onChange, onRemove };
}

describe("PortfolioGroupItemRow", () => {
  it("그룹 라벨과 레버리지 안내를 보여준다", () => {
    renderRow();
    expect(screen.getByText("나스닥 100")).toBeTruthy();
    expect(screen.getByText(/레버리지 종목은 배수만큼 노출로 계산해요/)).toBeTruthy();
  });

  it("대표 매수 후보에서 레버리지 멤버는 제외한다", () => {
    renderRow();
    const select = screen.getByRole("combobox", { name: "대표 매수 종목" });
    const values = Array.from((select as HTMLSelectElement).options).map((o) => o.value);
    expect(values).toEqual(["QQQ|NASDAQ", "QQQM|NASDAQ"]);
  });

  it("비중 입력은 숫자로, 빈 값은 0으로 넘긴다", () => {
    const { onChange } = renderRow();
    const input = screen.getByRole("spinbutton", { name: "나스닥 100 목표 비중" });
    fireEvent.change(input, { target: { value: "25.5" } });
    expect(onChange).toHaveBeenLastCalledWith(2, expect.objectContaining({ weight: 25.5 }));
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(2, expect.objectContaining({ weight: 0 }));
  });

  it("삭제 버튼은 인덱스로 onRemove를 부른다", () => {
    const { onRemove } = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "항목 삭제" }));
    expect(onRemove).toHaveBeenCalledWith(2);
  });

  it("멤버 빼기는 해당 종목을 members에서 지운다", () => {
    const { onChange } = renderRow();
    fireEvent.click(screen.getByRole("button", { name: "Invesco QQQM 그룹에서 빼기" }));
    const next = onChange.mock.calls[0]![1] as PortfolioItem;
    expect(next.group?.members.map((m) => m.ticker)).toEqual(["QLD"]);
  });

  it("국내 종목이 대표면 ISA·연금 대체 선택을 숨긴다", () => {
    renderRow(makeItem({ ticker: "133690", market: "KOSPI", name: "TIGER 미국나스닥100" }));
    expect(screen.queryByRole("combobox", { name: "ISA·연금 계좌 대체 매수" })).toBeNull();
  });
});
