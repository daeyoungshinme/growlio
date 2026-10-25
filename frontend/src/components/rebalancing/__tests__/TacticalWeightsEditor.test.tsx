import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import TacticalWeightsEditor from "@/components/rebalancing/TacticalWeightsEditor";

const TABLE = {
  RISK_ON: { QQQ: 50, SPY: 40, DIA: 0, QLD: 0, SSO: 0, CASH: 10 },
  NEUTRAL: { QQQ: 30, SPY: 40, DIA: 0, QLD: 0, SSO: 0, CASH: 30 },
  RISK_OFF: { QQQ: 10, SPY: 30, DIA: 0, QLD: 0, SSO: 0, CASH: 60 },
};

function renderEditor(props: Partial<Parameters<typeof TacticalWeightsEditor>[0]> = {}) {
  const onSave = vi.fn();
  render(
    <TacticalWeightsEditor
      regimeWeights={TABLE}
      isDefaultWeights
      tiltShiftPct={10}
      dipShiftPct={0}
      notifyEnabled
      saving={false}
      onSave={onSave}
      {...props}
    />,
  );
  fireEvent.click(screen.getByText("비중표 편집"));
  return { onSave };
}

const cell = (label: string) => screen.getByLabelText(label) as HTMLInputElement;
const saveBtn = () => screen.getByText("비중표 저장") as HTMLButtonElement;
const tiltOption = (label: string) =>
  within(screen.getByRole("group", { name: "나스닥·S&P 비중 조절폭" })).getByText(label);
const dipOption = (label: string) =>
  within(screen.getByRole("group", { name: "웅덩이 매수 투입폭" })).getByText(label);

describe("TacticalWeightsEditor", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("변경이 없으면 저장 버튼이 꺼져 있고, 기본값이면 되돌리기도 꺼져 있다", () => {
    renderEditor();
    expect(cell("공격 국면 QQQ 비중").value).toBe("50");
    expect(saveBtn().disabled).toBe(true);
    expect((screen.getByText("기본값으로") as HTMLButtonElement).disabled).toBe(true);
  });

  it("합계가 100이 아니면 경고하고 저장을 막는다", () => {
    renderEditor();
    fireEvent.change(cell("공격 국면 QQQ 비중"), { target: { value: "60" } });
    expect(screen.getByText(/합계 110%/)).toBeDefined();
    expect(screen.getByText(/100%가 되어야 해요/)).toBeDefined();
    expect(saveBtn().disabled).toBe(true);
  });

  it("유효한 변경은 비중표와 이동폭을 함께 저장한다", () => {
    const { onSave } = renderEditor();
    fireEvent.change(cell("공격 국면 QQQ 비중"), { target: { value: "60" } });
    fireEvent.change(cell("공격 국면 SPY 비중"), { target: { value: "30" } });
    fireEvent.click(tiltOption("20%p"));
    fireEvent.click(saveBtn());
    expect(onSave).toHaveBeenCalledWith({
      notify_enabled: true,
      regime_weights: { ...TABLE, RISK_ON: { QQQ: 60, SPY: 30, DIA: 0, QLD: 0, SSO: 0, CASH: 10 } },
      tilt_shift_pct: 20,
      dip_shift_pct: 0,
    });
  });

  it("DIA가 없는 기존 비중표는 0으로 채우고, DIA 비중을 넣어 저장할 수 있다", () => {
    const legacy = {
      RISK_ON: { QQQ: 50, SPY: 40, CASH: 10 },
      NEUTRAL: { QQQ: 30, SPY: 40, CASH: 30 },
      RISK_OFF: { QQQ: 10, SPY: 30, CASH: 60 },
    } as unknown as typeof TABLE;
    const { onSave } = renderEditor({ regimeWeights: legacy });
    expect(cell("공격 국면 DIA 비중").value).toBe("0");
    expect(saveBtn().disabled).toBe(true);
    fireEvent.change(cell("공격 국면 SPY 비중"), { target: { value: "20" } });
    fireEvent.change(cell("공격 국면 DIA 비중"), { target: { value: "20" } });
    fireEvent.click(saveBtn());
    expect(onSave.mock.calls[0][0].regime_weights.RISK_ON).toEqual({
      QQQ: 50,
      SPY: 20,
      DIA: 20,
      QLD: 0,
      SSO: 0,
      CASH: 10,
    });
  });

  it("이동폭만 바꿔도 저장할 수 있다", () => {
    const { onSave } = renderEditor();
    fireEvent.click(tiltOption("끔"));
    fireEvent.click(saveBtn());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ tilt_shift_pct: 0 }));
  });

  it("웅덩이 투입폭을 저장한다", () => {
    const { onSave } = renderEditor();
    fireEvent.click(dipOption("20%p"));
    fireEvent.click(saveBtn());
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ dip_shift_pct: 20 }));
  });

  it("레버리지 비중을 넣으면 경고하고, 방어 국면이면 추가로 경고한다", () => {
    renderEditor();
    expect(screen.queryByText(/레버리지 ETF라/)).toBeNull();
    fireEvent.change(cell("공격 국면 QLD 비중"), { target: { value: "20" } });
    expect(screen.getByText(/레버리지 ETF라/)).toBeDefined();
    expect(screen.queryByText(/방어 국면에 레버리지/)).toBeNull();
    fireEvent.change(cell("방어 국면 SSO 비중"), { target: { value: "10" } });
    expect(screen.getByText(/방어 국면에 레버리지/)).toBeDefined();
  });

  it("빈칸·범위 밖 값은 합계를 계산하지 않는다", () => {
    renderEditor();
    fireEvent.change(cell("방어 국면 현금 비중"), { target: { value: "" } });
    expect(screen.getByText(/합계 —/)).toBeDefined();
    fireEvent.change(cell("방어 국면 현금 비중"), { target: { value: "120" } });
    expect(saveBtn().disabled).toBe(true);
  });

  it("직접 정한 비중표면 기본값으로 되돌릴 수 있다", () => {
    const { onSave } = renderEditor({ isDefaultWeights: false, tiltShiftPct: 15, dipShiftPct: 20 });
    fireEvent.click(screen.getByText("기본값으로"));
    expect(onSave).toHaveBeenCalledWith({
      notify_enabled: true,
      regime_weights: null,
      tilt_shift_pct: 10,
      dip_shift_pct: 0,
    });
  });
});
