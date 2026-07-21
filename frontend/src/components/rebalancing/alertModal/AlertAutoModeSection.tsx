import { Loader2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import type { MarketSignalResponse } from "@/api/marketSignals";
import { fetchSettings } from "@/api/settings";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { INPUT_SM } from "@/constants/inputStyles";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import {
  STRATEGY_OPTIONS,
  BUY_WAIT_MINUTES_OPTIONS,
  MARKET_CONDITION_OPTIONS,
  TAX_IMPACT_GATE_OPTIONS,
} from "@/constants/rebalancingConfig";
import { fmtKrw } from "@/utils/format";
import MarketSignalLevelBadge from "@/components/rebalancing/MarketSignalLevelBadge";

const inputClass = `w-full ${INPUT_SM}`;

interface Props {
  form: RebalancingAlertFormState;
  targetAccountId?: string;
  targetAccountName?: string;
  autoExecutionAccounts: AssetAccount[];
  canSwitchToPerAccount?: boolean;
  switchToPerAccountMut: { mutate: () => void; isPending: boolean };
  marketSignal?: MarketSignalResponse;
}

export function AlertAutoModeSection({
  form,
  targetAccountId,
  targetAccountName,
  autoExecutionAccounts,
  canSwitchToPerAccount,
  switchToPerAccountMut,
  marketSignal,
}: Props) {
  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  return (
    <div className="space-y-3 p-4 rounded-xl bg-orange-50 dark:bg-orange-950 border border-orange-200 dark:border-orange-800">
      <p className="text-xs text-orange-600 dark:text-orange-400 font-medium">
        ⚠️ 자동 실행 모드는 실제 매매 주문이 발생합니다. 조건 충족 시 계획을 이메일로 먼저
        알려드립니다 — 매수는 대기시간 후 자동 실행(취소 가능), 매도는 이메일 승인이 필요하며 당일
        장마감까지 미응답 시 자동 취소됩니다.
        {settingsData && (
          <>
            {" "}
            안전장치로 1건당 거래대금은 {fmtKrw(settingsData.auto_rebalancing_max_order_value_krw)}
            을 넘지 않도록 자동으로 축소됩니다.
          </>
        )}
      </p>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          실행 계좌
        </label>
        {targetAccountId ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
            <span>{targetAccountName ?? "이 계좌"}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">
              (계좌별 독립 설정 대상)
            </span>
          </div>
        ) : autoExecutionAccounts.length === 0 ? (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            KIS/키움 연동 계좌가 없습니다. 자산관리에서 계좌를 추가해주세요.
          </p>
        ) : autoExecutionAccounts.length === 1 ? (
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 dark:bg-gray-800 text-sm text-gray-700 dark:text-gray-300">
            <span>{autoExecutionAccounts[0].name}</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">(자동 선택)</span>
          </div>
        ) : (
          <select
            className={inputClass}
            value={form.accountId}
            onChange={(e) => form.setAccountId(e.target.value)}
          >
            <option value="">계좌 선택</option>
            {autoExecutionAccounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        )}
      </div>

      {!targetAccountId && canSwitchToPerAccount && (
        <button
          onClick={() => switchToPerAccountMut.mutate()}
          disabled={switchToPerAccountMut.isPending}
          className="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
        >
          {switchToPerAccountMut.isPending && <Loader2 size={12} className="animate-spin" />}
          여러 계좌에 각각 자동 실행 설정하기 →
        </button>
      )}

      <div className="space-y-2">
        {STRATEGY_OPTIONS.map(({ value: s, label, desc }) => (
          <label
            key={s}
            className={`flex items-start gap-2 p-2.5 rounded-lg border cursor-pointer transition-colors ${
              form.strategy === s
                ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                : "border-gray-300 dark:border-gray-600 hover:border-gray-400"
            }`}
          >
            <input
              type="radio"
              name="strategy"
              value={s}
              checked={form.strategy === s}
              onChange={() => form.setStrategy(s)}
              className="mt-0.5 accent-blue-600"
            />
            <div>
              <div className="text-xs font-medium text-gray-800 dark:text-gray-200">{label}</div>
              <div className="text-xs text-gray-400 dark:text-gray-500">{desc}</div>
            </div>
          </label>
        ))}
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          자동 실행 시각 (KST)
        </label>
        <input
          type="time"
          min="09:00"
          max="15:00"
          step={300}
          value={form.autoExecutionTime}
          onChange={(e) => form.setAutoExecutionTime(e.target.value)}
          className={inputClass}
        />
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          장 중(09:00~15:00 KST) 지정 시각에 자동 실행됩니다.
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          매수 대기시간
        </label>
        <select
          className={inputClass}
          value={form.buyWaitMinutes}
          onChange={(e) => form.setBuyWaitMinutes(Number(e.target.value))}
        >
          {BUY_WAIT_MINUTES_OPTIONS.map(({ value, label }) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
          매수 계획을 이메일로 알린 뒤 이 시간만큼 대기 후 자동 실행됩니다. 그동안 앱이나 이메일에서
          취소할 수 있습니다.
        </p>
      </div>

      <div>
        <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          주문 유형
        </label>
        <select
          className={inputClass}
          value={form.orderType}
          onChange={(e) => form.setOrderType(e.target.value as "MARKET" | "LIMIT")}
        >
          <option value="MARKET">시장가</option>
          <option value="LIMIT">지정가</option>
        </select>
        {form.orderType === "LIMIT" && (
          <p className="mt-1.5 text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
            자동 실행 시 분석 시점의 현재가를 지정가로 사용합니다. 가격 변동으로 미체결될 수
            있습니다.
          </p>
        )}
      </div>

      {/* ── 시장 신호 연동 ── */}
      <div className="pt-1 border-t border-orange-200/30 dark:border-orange-800/30">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">시장 신호 연동</p>
          {marketSignal && (
            <div className="flex items-center gap-1.5 text-xs text-gray-400">
              현재: <MarketSignalLevelBadge level={marketSignal.composite_level} size="xs" />
            </div>
          )}
        </div>
        <select
          className={inputClass}
          value={form.marketConditionMode}
          onChange={(e) =>
            form.setMarketConditionMode(e.target.value as "DISABLED" | "CAUTIOUS" | "STRICT")
          }
        >
          {MARKET_CONDITION_OPTIONS.map(({ value, label, desc }) => (
            <option key={value} value={value}>
              {label} — {desc}
            </option>
          ))}
        </select>
      </div>

      {/* ── 세금영향 게이트 ── */}
      <div className="pt-1 border-t border-orange-200/30 dark:border-orange-800/30">
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">세금영향 게이트</p>
        <select
          className={inputClass}
          value={form.taxImpactGateMode}
          onChange={(e) => form.setTaxImpactGateMode(e.target.value as "DISABLED" | "ENABLED")}
        >
          {TAX_IMPACT_GATE_OPTIONS.map(({ value, label, desc }) => (
            <option key={value} value={value}>
              {label} — {desc}
            </option>
          ))}
        </select>
        {form.taxImpactGateMode === "ENABLED" && (
          <div className="mt-2">
            <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
              추정 양도세 상한 (원)
            </label>
            <input
              type="number"
              min={1}
              step={10000}
              placeholder="예: 500000"
              value={form.maxTaxImpactKrw ?? ""}
              onChange={(e) =>
                form.setMaxTaxImpactKrw(e.target.value === "" ? null : Number(e.target.value))
              }
              className={inputClass}
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              매도로 인한 추정 양도세가 이 금액을 넘으면 이번 자동 실행 계획을 만들지 않고
              보류합니다 (참고용 추정치 — 앱에서 알림으로 안내).
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
