import { z } from "zod";

export const portfolioItemSchema = z.object({
  ticker: z.string().min(1, "티커를 입력해주세요"),
  name: z.string(),
  market: z.string().min(1, "시장을 선택해주세요"),
  weight: z.number().min(0, "비중은 0 이상이어야 합니다").max(100, "비중은 100 이하여야 합니다"),
});

export const portfolioCreateSchema = z
  .object({
    name: z
      .string()
      .min(1, "포트폴리오 이름을 입력해주세요")
      .max(100, "이름은 100자 이하여야 합니다"),
    items: z
      .array(portfolioItemSchema)
      .min(1, "종목을 하나 이상 추가해주세요")
      .max(50, "종목은 최대 50개까지 추가할 수 있습니다"),
    base_type: z.enum(["STOCK_ONLY", "TOTAL_ASSETS"]).optional(),
    account_ids: z.array(z.string().uuid()).nullable().optional(),
  })
  .refine(
    (d) => {
      const total = d.items.reduce((s, i) => s + i.weight, 0);
      return Math.abs(total - 100) < 0.01;
    },
    { message: "종목 비중 합계가 100%여야 합니다", path: ["items"] },
  );

export type PortfolioCreateFormData = z.infer<typeof portfolioCreateSchema>;
export type PortfolioItemFormData = z.infer<typeof portfolioItemSchema>;
