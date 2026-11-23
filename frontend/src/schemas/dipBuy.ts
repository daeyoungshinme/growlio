import { z } from "zod";

/** 낙폭 추매 여윳돈·알림 방식 — 백엔드 `DipBuySettingsUpsert`와 같은 규칙(plans/148) */
export const dipBuySettingsSchema = z
  .object({
    reserve_krw: z
      .number({ error: "여윳돈을 입력해주세요" })
      .min(0, "여윳돈은 0 이상이어야 합니다")
      .max(100_000_000_000, "금액이 너무 큽니다"),
    notify_mode: z.enum(["ON_REACH", "MONTHLY_DAY"]),
    notify_day: z.number().int().min(1).max(28).nullable(),
    is_active: z.boolean(),
  })
  .refine((v) => v.notify_mode !== "MONTHLY_DAY" || v.notify_day != null, {
    message: "매달 알림 받을 날짜를 정해주세요",
    path: ["notify_day"],
  });

/** 지수별 추매 규칙 — 백엔드 `DipBuyRuleUpsert`·`dip_buy_calculator.validate_tiers`와 같은 규칙(plans/147·148) */
export const dipBuyRuleSchema = z
  .object({
    index_ticker: z.enum(["QQQ", "SPY"]),
    allocation_pct: z
      .number({ error: "여윳돈 배분을 입력해주세요" })
      .min(1, "여윳돈 배분은 1~100% 사이로 정해주세요")
      .max(100, "여윳돈 배분은 1~100% 사이로 정해주세요"),
    tiers: z
      .array(
        z.object({
          drawdown_pct: z
            .number({ error: "낙폭을 입력해주세요" })
            .min(1, "낙폭은 1~60% 사이로 정해주세요")
            .max(60, "낙폭은 1~60% 사이로 정해주세요"),
          ratio_pct: z
            .number({ error: "비율을 입력해주세요" })
            .min(1, "구간 비율은 1~100% 사이로 정해주세요")
            .max(100, "구간 비율은 1~100% 사이로 정해주세요"),
        }),
      )
      .min(1, "추매 구간은 1~3개로 정해주세요")
      .max(3, "추매 구간은 1~3개로 정해주세요"),
    is_active: z.boolean(),
  })
  .refine(
    (v) => v.tiers.every((t, i) => i === 0 || t.drawdown_pct > (v.tiers[i - 1]?.drawdown_pct ?? 0)),
    {
      message: "구간 낙폭은 얕은 것부터 깊은 순서로, 서로 다르게 정해주세요",
      path: ["tiers"],
    },
  )
  .refine((v) => v.tiers.reduce((sum, t) => sum + t.ratio_pct, 0) <= 100, {
    message: "구간 비율 합계는 100%를 넘을 수 없어요",
    path: ["tiers"],
  });
