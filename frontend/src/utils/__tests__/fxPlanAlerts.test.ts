import { describe, expect, it } from "vitest";
import type { ExchangeRateAlert } from "@/api/alerts";
import type { FxTranche } from "@/api/invest";
import { planAlertState, rateKey, syncButtonLabel, syncToastMessage } from "@/utils/fxPlanAlerts";

const alert = (target_rate: number, over: Partial<ExchangeRateAlert> = {}): ExchangeRateAlert => ({
  id: `a-${target_rate}-${over.fx_need_id ?? over.portfolio_id ?? "m"}`,
  target_rate,
  direction: "BELOW",
  is_active: true,
  max_trigger_count: 1,
  trigger_count: 0,
  triggered_at: null,
  created_at: "2026-11-11T00:00:00Z",
  ...over,
});

const tranches: FxTranche[] = [
  { label: "지금", target_rate: null, usd: 300, krw_estimate: 420_000 },
  { label: "1,380원 이하", target_rate: 1380, usd: 350, krw_estimate: 483_000 },
];

const planAlert = (rate: number, over: Partial<ExchangeRateAlert>) =>
  alert(rate, { source: "FX_PLAN", planned_usd: 350, ...over });

describe("planAlertState scope (plans/123)", () => {
  it("추가 환전 항목 범위는 그 항목의 알림만 센다", () => {
    const alerts = [
      planAlert(1380, { fx_need_id: "n1" }),
      planAlert(1380, { fx_need_id: "n2" }),
      planAlert(1380, { portfolio_id: "p1" }),
    ];
    const state = planAlertState(alerts, tranches, { fxNeedId: "n1" });
    expect(state.planAlertCount).toBe(1);
    expect(state.inSync).toBe(true);
  });

  it("포트폴리오 범위는 항목 알림을 제외한다 — 포트폴리오가 없어도(null) 항목 알림을 자기 것으로 보지 않는다", () => {
    const alerts = [planAlert(1380, { fx_need_id: "n1", portfolio_id: null })];
    const state = planAlertState(alerts, tranches, { portfolioId: null });
    expect(state.planAlertCount).toBe(0);
    expect(state.inSync).toBe(false);
  });

  it("같은 목표의 직접 등록 알림은 manualRates로 표시한다", () => {
    const state = planAlertState([alert(1380)], tranches, { fxNeedId: "n1" });
    expect(state.manualRates.has(rateKey(1380))).toBe(true);
    expect(state.inSync).toBe(true);
  });
});

describe("syncButtonLabel", () => {
  it("상태별 문구", () => {
    const empty = planAlertState([], tranches, { fxNeedId: "n1" });
    expect(syncButtonLabel(empty, false, false)).toBe("알림 목록 확인 중");
    expect(syncButtonLabel(empty, true, true)).toBe("등록 중…");
    expect(syncButtonLabel(empty, true, false)).toBe("목표 환율 알림 등록");

    const stale = planAlertState([planAlert(1400, { fx_need_id: "n1" })], tranches, {
      fxNeedId: "n1",
    });
    expect(syncButtonLabel(stale, true, false)).toBe("알림을 새 계획으로 바꾸기");

    const release = planAlertState([planAlert(1400, { fx_need_id: "n1" })], [], { fxNeedId: "n1" });
    expect(syncButtonLabel(release, true, false)).toBe("이 계획으로 등록한 알림 1건 해제");
  });
});

describe("포트폴리오 계획끼리 같은 목표 알림 공유", () => {
  it("다른 포트폴리오 계획의 미발동 알림이 같은 목표면 sharedRates로 보고 등록된 것으로 본다", () => {
    const state = planAlertState([planAlert(1380, { portfolio_id: "p2" })], tranches, {
      portfolioId: "p1",
    });
    expect(state.sharedRates.has(rateKey(1380))).toBe(true);
    expect(state.planAlertCount).toBe(0);
    expect(state.inSync).toBe(true);
  });

  it("이 계획에도 같은 목표 알림이 있으면 맞추기 전까지 inSync가 아니다 — 맞추면 서버가 하나로 줄인다", () => {
    const alerts = [
      planAlert(1380, { portfolio_id: "p2" }),
      planAlert(1380, { portfolio_id: "p1" }),
    ];
    const state = planAlertState(alerts, tranches, { portfolioId: "p1" });
    expect(state.inSync).toBe(false);
  });

  it("발동된 다른 계획 알림·추가 환전 항목 범위는 공유하지 않는다", () => {
    const fired = planAlert(1380, { portfolio_id: "p2", triggered_at: "2026-11-11T00:00:00Z" });
    expect(planAlertState([fired], tranches, { portfolioId: "p1" }).sharedRates.size).toBe(0);
    const forNeed = planAlertState([planAlert(1380, { portfolio_id: "p2" })], tranches, {
      fxNeedId: "n1",
    });
    expect(forNeed.sharedRates.size).toBe(0);
    expect(forNeed.inSync).toBe(false);
  });

  it("토스트에 함께 쓰는 목표 수를 알린다", () => {
    expect(
      syncToastMessage(
        { created: 0, updated: 0, removed: 1, skipped_manual: 0, skipped_shared: 1 },
        1,
      ),
    ).toBe(
      "같은 목표의 알림이 이미 있어 새로 만들지 않았습니다 · 옛 목표 1건 해제 · 다른 포트폴리오 계획과 같은 목표 1건은 그 알림을 함께 사용",
    );
  });
});
