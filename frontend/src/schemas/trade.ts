import { z } from "zod";

export const tradeSchema = z.object({
  account_id: z.string().min(1, "계좌를 선택해주세요"),
  side: z.enum(["BUY", "SELL"]),
  ticker: z.string().trim().min(1, "종목을 선택해주세요"),
  market: z.string().min(1, "종목을 선택해주세요"),
  qty: z.number({ error: "수량을 입력해주세요" }).positive("수량은 0보다 커야 합니다"),
  price_krw: z.number({ error: "단가를 입력해주세요" }).positive("단가는 0보다 커야 합니다"),
  fee: z.number().min(0, "수수료는 0 이상이어야 합니다").optional(),
  trade_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "날짜 형식이 올바르지 않습니다"),
  notes: z.string().max(500, "메모는 500자 이하여야 합니다").optional(),
});

export type TradeFormData = z.infer<typeof tradeSchema>;
