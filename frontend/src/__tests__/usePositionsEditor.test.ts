import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { usePositionsEditor, type Position } from "@/hooks/usePositionsEditor";

vi.mock("@/api/assets", () => ({
  fetchStockPrice: vi.fn(),
  searchStocks: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/utils/error", () => ({
  extractErrorMessage: vi.fn((e, fallback) => fallback),
}));

const makePos = (overrides: Partial<Position> = {}): Position => ({
  ticker: "005930",
  name: "삼성전자",
  market: "KOSPI",
  qty: 10,
  avg_price: 70000,
  avg_price_usd: null,
  usd_rate: null,
  current_price: 75000,
  ...overrides,
});

describe("usePositionsEditor", () => {
  beforeEach(() => vi.clearAllMocks());

  it("초기 rows가 올바르게 설정된다", () => {
    const initial = [makePos()];
    const { result } = renderHook(() => usePositionsEditor(initial, null));
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].ticker).toBe("005930");
  });

  it("liveRows가 P&L 계산 값을 포함한다", () => {
    const pos = makePos({ qty: 10, avg_price: 70000, current_price: 75000 });
    const { result } = renderHook(() => usePositionsEditor([pos], null));
    const liveRow = result.current.liveRows[0];
    expect(liveRow.invested_amount).toBe(700000);
    expect(liveRow.value_amount).toBe(750000);
    expect(liveRow.pnl).toBe(50000);
    expect(liveRow.pnl_pct).toBeCloseTo(7.14, 1);
  });

  it("current_price가 없으면 avg_price를 사용한다", () => {
    const pos = makePos({ qty: 10, avg_price: 70000, current_price: null });
    const { result } = renderHook(() => usePositionsEditor([pos], null));
    expect(result.current.liveRows[0].value_amount).toBe(700000);
  });

  it("addRow가 새 빈 행을 추가한다", () => {
    const { result } = renderHook(() => usePositionsEditor([], null));
    act(() => { result.current.addRow(); });
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].ticker).toBe("");
  });

  it("removeRow가 지정 인덱스 행을 삭제한다", () => {
    const initial = [makePos({ ticker: "005930" }), makePos({ ticker: "000660" })];
    const { result } = renderHook(() => usePositionsEditor(initial, null));
    act(() => { result.current.removeRow(0); });
    expect(result.current.rows).toHaveLength(1);
    expect(result.current.rows[0].ticker).toBe("000660");
  });

  it("setRow가 특정 행의 필드를 업데이트한다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], null));
    act(() => { result.current.setRow(0, { qty: 20 }); });
    expect(result.current.rows[0].qty).toBe(20);
  });

  it("handleNameChange가 이름을 업데이트하고 종목 검색을 실행한다", async () => {
    const { result } = renderHook(() => usePositionsEditor([makePos({ name: "" })], null));
    act(() => { result.current.handleNameChange(0, "삼성"); });
    expect(result.current.rows[0].name).toBe("삼성");
    expect(result.current.suggestIdx).toBe(0);
  });

  it("handleNameChange 빈 문자열은 제안을 지운다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], null));
    act(() => { result.current.handleNameChange(0, "삼성"); });
    act(() => { result.current.handleNameChange(0, ""); });
    expect(result.current.suggestIdx).toBeNull();
  });

  it("handleSelectSuggestion이 행을 업데이트하고 제안을 지운다", async () => {
    const { fetchStockPrice } = await import("@/api/assets");
    vi.mocked(fetchStockPrice).mockResolvedValue({ price_krw: 75000, price_usd: null, usd_rate: null });

    const { result } = renderHook(() => usePositionsEditor([makePos({ ticker: "" })], null));
    const suggestion = { ticker: "000660", name: "SK하이닉스", market: "KOSPI", exchange: "KRX" };
    act(() => { result.current.handleSelectSuggestion(0, suggestion); });
    expect(result.current.rows[0].ticker).toBe("000660");
    expect(result.current.rows[0].name).toBe("SK하이닉스");
    expect(result.current.suggestIdx).toBeNull();
    await waitFor(() => expect(result.current.rows[0].current_price).toBe(75000));
  });

  it("handleAvgPriceUsd가 USD 가격을 KRW로 환산한다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], 1350));
    act(() => { result.current.handleAvgPriceUsd(0, "100"); });
    expect(result.current.rows[0].avg_price_usd).toBe(100);
    expect(result.current.rows[0].avg_price).toBe(135000);
    expect(result.current.rows[0].usd_rate).toBe(1350);
  });

  it("handleAvgPriceUsd 빈 문자열은 0으로 처리한다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], 1350));
    act(() => { result.current.handleAvgPriceUsd(0, ""); });
    expect(result.current.rows[0].avg_price_usd).toBeNull();
    expect(result.current.rows[0].avg_price).toBe(0);
  });

  it("handleCurrentPriceUsd가 현재가를 업데이트한다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], 1350));
    act(() => { result.current.handleCurrentPriceUsd(0, "50"); });
    expect(result.current.rows[0].current_price_usd).toBe(50);
    expect(result.current.rows[0].current_price).toBe(67500);
  });

  it("handleCurrentPriceUsd 빈 문자열은 null로 처리한다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos()], 1350));
    act(() => { result.current.handleCurrentPriceUsd(0, ""); });
    expect(result.current.rows[0].current_price_usd).toBeNull();
    expect(result.current.rows[0].current_price).toBeNull();
  });

  it("enrichRows가 해외 종목 current_price_usd를 계산한다", () => {
    const { result } = renderHook(() => usePositionsEditor([], 1350));
    const pos = makePos({ market: "NASDAQ", current_price: 135000, usd_rate: 1350, current_price_usd: null });
    const enriched = result.current.enrichRows([pos]);
    expect(enriched[0].current_price_usd).toBeCloseTo(100, 2);
  });

  it("enrichRows가 _rowKey가 없으면 ticker-market 키를 생성한다", () => {
    const { result } = renderHook(() => usePositionsEditor([], null));
    const pos = makePos({ _rowKey: undefined });
    const enriched = result.current.enrichRows([pos]);
    expect(enriched[0]._rowKey).toBe("005930-KOSPI");
  });

  it("handleSelectSuggestion에서 가격 조회 실패 시 toast를 호출한다", async () => {
    const { fetchStockPrice } = await import("@/api/assets");
    const { toast } = await import("@/utils/toast");
    vi.mocked(fetchStockPrice).mockRejectedValue(new Error("가격 조회 실패"));

    const { result } = renderHook(() => usePositionsEditor([makePos({ ticker: "" })], null));
    const suggestion = { ticker: "000660", name: "SK하이닉스", market: "KOSPI", exchange: "KRX" };
    await act(async () => {
      result.current.handleSelectSuggestion(0, suggestion);
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(toast).toHaveBeenCalled();
  });

  it("removeRow가 현재 suggestIdx 행 삭제 시 제안을 지운다", () => {
    const { result } = renderHook(() => usePositionsEditor([makePos(), makePos()], null));
    act(() => { result.current.setSuggestIdx(0); });
    act(() => { result.current.removeRow(0); });
    expect(result.current.suggestIdx).toBeNull();
  });
});
