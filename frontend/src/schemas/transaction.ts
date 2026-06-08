import { z } from "zod";

export const transactionSchema = z.object({
  transaction_type: z.enum(["DEPOSIT", "WITHDRAWAL", "DIVIDEND"]),
  amount: z.number({ error: "금액을 입력해주세요" }).positive("금액은 0보다 커야 합니다"),
  transaction_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "날짜 형식이 올바르지 않습니다"),
  ticker: z.string().optional(),
  notes: z.string().max(500, "메모는 500자 이하여야 합니다").optional(),
});

export type TransactionFormData = z.infer<typeof transactionSchema>;
