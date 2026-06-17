import { z } from "zod";

const VALID_MARKETS = [
  "KOSPI",
  "KOSDAQ",
  "KONEX",
  "NYSE",
  "NASDAQ",
  "AMEX",
  "TSE",
  "HKEX",
  "LSE",
] as const;

export const realEstateDetailsSchema = z.object({
  address: z.string().min(1, "주소를 입력해주세요"),
  property_type: z.string().min(1, "부동산 유형을 선택해주세요"),
  purchase_price_krw: z.number().positive("매입가는 0보다 커야 합니다").optional(),
  purchase_date: z.string().optional(),
  mortgage_balance_krw: z.number().min(0, "모기지 잔액은 0 이상이어야 합니다").optional(),
});

export const assetAccountCreateSchema = z.object({
  name: z.string().min(1, "계좌명을 입력해주세요").max(100, "계좌명은 100자 이하여야 합니다"),
  asset_type: z.string().min(1, "자산 유형을 선택해주세요"),
  data_source: z.string().optional(),
  institution: z.string().optional(),
  kis_account_no: z
    .string()
    .regex(/^\d{8}-\d{2}$|^\d{10}$/, "KIS 계좌번호 형식이 올바르지 않습니다 (예: 12345678-01)")
    .optional()
    .or(z.literal("")),
  kis_app_key: z.string().optional(),
  kis_app_secret: z.string().optional(),
  kiwoom_account_no: z.string().optional(),
  kiwoom_app_key: z.string().optional(),
  kiwoom_app_secret: z.string().optional(),
  ob_fintech_use_no: z.string().optional(),
  is_mock_mode: z.boolean().optional(),
  manual_amount: z.number().positive("금액은 0보다 커야 합니다").optional(),
  deposit_krw: z.number().min(0, "예수금은 0 이상이어야 합니다").optional(),
  deposit_usd: z.number().min(0, "USD 예수금은 0 이상이어야 합니다").optional(),
  notes: z.string().max(500).optional(),
  sort_order: z.number().int().optional(),
  real_estate_details: realEstateDetailsSchema.optional(),
  include_in_total: z.boolean().optional(),
});

export const manualPositionSchema = z.object({
  ticker: z.string().min(1, "티커를 입력해주세요").max(20, "티커는 20자 이하여야 합니다"),
  name: z.string().min(1, "종목명을 입력해주세요").max(200, "종목명은 200자 이하여야 합니다"),
  market: z.enum(VALID_MARKETS, { error: "유효하지 않은 시장입니다" }),
  qty: z
    .number()
    .positive("수량은 0보다 커야 합니다")
    .max(1_000_000, "수량은 100만 이하여야 합니다"),
  avg_price: z.number().positive("평균단가는 0보다 커야 합니다"),
  avg_price_usd: z.number().positive("달러 평균단가는 0보다 커야 합니다").optional().nullable(),
  usd_rate: z.number().min(0).max(9999, "환율은 10,000 미만이어야 합니다").optional().nullable(),
  current_price: z.number().optional().nullable(),
});

export type AssetAccountCreateFormData = z.infer<typeof assetAccountCreateSchema>;
export type ManualPositionFormData = z.infer<typeof manualPositionSchema>;
