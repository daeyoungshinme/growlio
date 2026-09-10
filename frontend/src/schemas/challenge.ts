import { z } from "zod";

const monthRe = /^\d{4}-(0[1-9]|1[0-2])$/;

export const challengeFormSchema = z
  .object({
    title: z.string().trim().min(1, "제목을 입력해주세요").max(100, "제목은 100자 이하여야 합니다"),
    challenge_type: z.enum(["DEPOSIT", "RETURN_PCT", "TARGET_VALUE"]),
    target_amount: z.number().nonnegative("금액은 0 이상이어야 합니다").nullable().optional(),
    target_pct: z.number().min(-100).max(1000).nullable().optional(),
    target_months: z.number().int().min(1).max(600).nullable().optional(),
    account_id: z.string().nullable().optional(),
    start_month: z.string().regex(monthRe, "월 형식은 YYYY-MM 이어야 합니다"),
    deadline_month: z
      .string()
      .regex(monthRe, "월 형식은 YYYY-MM 이어야 합니다")
      .nullable()
      .optional(),
    reminder_enabled: z.boolean(),
  })
  .superRefine((v, ctx) => {
    if (
      v.challenge_type === "RETURN_PCT" &&
      (v.target_pct === null || v.target_pct === undefined)
    ) {
      ctx.addIssue({ code: "custom", message: "목표 수익률을 입력해주세요", path: ["target_pct"] });
    }
    if (v.challenge_type === "TARGET_VALUE" && !v.target_amount) {
      ctx.addIssue({
        code: "custom",
        message: "목표 금액을 입력해주세요",
        path: ["target_amount"],
      });
    }
    if (v.challenge_type !== "DEPOSIT" && v.account_id) {
      ctx.addIssue({
        code: "custom",
        message: "수익률/평가금액 챌린지는 전체 투자자산 기준만 지원합니다",
        path: ["account_id"],
      });
    }
  });

export type ChallengeFormData = z.infer<typeof challengeFormSchema>;
