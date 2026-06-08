import { z } from "zod";

export const investGoalSchema = z.object({
  annual_investment_goal: z
    .number({ error: "금액을 입력해주세요" })
    .min(0, "목표 금액은 0 이상이어야 합니다")
    .optional(),
  target_asset_amount: z
    .number({ error: "금액을 입력해주세요" })
    .min(0, "목표 자산은 0 이상이어야 합니다")
    .optional(),
  target_year: z
    .number({ error: "연도를 입력해주세요" })
    .int("정수 연도를 입력해주세요")
    .min(2020, "2020년 이후 연도를 입력해주세요")
    .max(2100, "2100년 이전 연도를 입력해주세요")
    .optional(),
});

export type InvestGoalFormData = z.infer<typeof investGoalSchema>;
