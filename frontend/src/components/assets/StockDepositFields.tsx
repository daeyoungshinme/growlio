import AmountUnitButtons from "@/components/common/AmountUnitButtons";
import { fmtKrw } from "@/utils/format";

interface Props {
  mode: "create" | "edit";
  depositKrw: number | undefined;
  depositUsd: number | undefined;
  setDepositKrw: (v: number | undefined) => void;
  setDepositUsd: (v: number | undefined) => void;
  usdRate: number | null;
  usdAsKrw: number;
  totalKrw: number;
  hasAnyDeposit: boolean;
}

// 신규 등록(MANUAL) / 편집 모드(KIS·키움 수동 보정) 공용 예수금 입력 필드
export default function StockDepositFields({
  mode,
  depositKrw,
  depositUsd,
  setDepositKrw,
  setDepositUsd,
  usdRate,
  usdAsKrw,
  totalKrw,
  hasAnyDeposit,
}: Props) {
  if (mode === "create") {
    return (
      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">예수금</label>
        <div>
          <label htmlFor="stock-deposit-krw" className="text-xs text-gray-500 dark:text-gray-400">
            원화 예수금
          </label>
          <div className="relative mt-0.5">
            <input
              id="stock-deposit-krw"
              type="number"
              inputMode="decimal"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={depositKrw ?? ""}
              onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))}
              placeholder="0"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">원</span>
          </div>
          <AmountUnitButtons onAdd={(delta) => setDepositKrw((depositKrw ?? 0) + delta)} />
        </div>
        <div>
          <label htmlFor="stock-deposit-usd" className="text-xs text-gray-500 dark:text-gray-400">
            외화 예수금 (USD)
          </label>
          <div className="relative mt-0.5">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">$</span>
            <input
              id="stock-deposit-usd"
              type="number"
              inputMode="decimal"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg pl-6 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={depositUsd ?? ""}
              onChange={(e) => setDepositUsd(e.target.value === "" ? undefined : Number(e.target.value))}
              placeholder="0"
            />
          </div>
          {(depositUsd ?? 0) > 0 && (
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              {usdRate == null
                ? "환율 정보를 불러오는 중..."
                : `≈ ${fmtKrw(usdAsKrw)} (환율 ${usdRate.toLocaleString()}원/USD)`}
            </p>
          )}
        </div>
        {hasAnyDeposit && (
          <div className="flex justify-between items-center pt-1 border-t border-gray-100 dark:border-gray-700">
            <span className="text-xs text-gray-500 dark:text-gray-400">합계</span>
            <span className="text-sm font-medium text-gray-900 dark:text-gray-50">{fmtKrw(totalKrw)}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium text-gray-700 dark:text-gray-300">예수금 (수동 보정)</label>
      <div className="relative">
        <input
          type="number"
          inputMode="decimal"
          className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={depositKrw ?? ""}
          onChange={(e) => setDepositKrw(e.target.value === "" ? undefined : Number(e.target.value))}
          placeholder="원화 예수금"
        />
        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">원</span>
      </div>
      <AmountUnitButtons onAdd={(delta) => setDepositKrw((depositKrw ?? 0) + delta)} />
      <div className="relative">
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">$</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.01"
          className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg pl-6 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={depositUsd ?? ""}
          onChange={(e) => setDepositUsd(e.target.value === "" ? undefined : Number(e.target.value))}
          placeholder="외화 예수금 (USD)"
        />
      </div>
      {(depositUsd ?? 0) > 0 && usdRate != null && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          ≈ {fmtKrw(usdAsKrw)} (환율 {usdRate.toLocaleString()}원/USD)
        </p>
      )}
    </div>
  );
}
