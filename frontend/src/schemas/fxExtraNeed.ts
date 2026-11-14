import { z } from "zod";

/** 추가 환전 항목(여행 등) 입력 — 백엔드 `FxExtraNeedCreate`와 같은 범위(plans/123) */
export const fxExtraNeedSchema = z
  .object({
    name: z.string().trim().min(1, "이름을 입력해주세요").max(40, "이름은 40자 이하여야 합니다"),
    amount_usd: z
      .number({ error: "필요한 금액을 입력해주세요" })
      .positive("필요한 금액은 0보다 커야 합니다")
      .max(100_000_000, "금액이 너무 큽니다"),
    exchanged_usd: z
      .number()
      .min(0, "이미 환전한 금액은 0 이상이어야 합니다")
      .max(100_000_000, "금액이 너무 큽니다"),
    due_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "필요일을 선택해주세요"),
  })
  .refine((v) => v.exchanged_usd <= v.amount_usd, {
    message: "이미 환전한 금액이 필요한 금액보다 클 수 없습니다",
    path: ["exchanged_usd"],
  });
