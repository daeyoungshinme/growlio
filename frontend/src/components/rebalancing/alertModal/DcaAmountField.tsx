import { useQuery } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { exchangeRateQuery, portfoliosQuery } from "@/api/queryOptions";
import { INPUT_SM } from "@/constants/inputStyles";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { DCA_AMOUNT_MIN_KRW, splitDcaAmount } from "@/utils/dcaAutoBuy";

interface Props {
  form: RebalancingAlertFormState;
  portfolioId: string;
  autoExecutionAccounts: AssetAccount[];
}

/** 정기 적립 정액(plans/120) — 매회 매수 금액 입력 + 목표 비중대로 나눈 종목별 미리보기.
 * 비워 두면 예전처럼 예수금 전체로 목표 비중을 채운다. */
export function DcaAmountField({ form, portfolioId, autoExecutionAccounts }: Props) {
  const { data: portfolios } = useQuery(portfoliosQuery);
  const { data: rate } = useQuery(exchangeRateQuery);
  const portfolio = portfolios?.find((p) => p.id === portfolioId);
  const account = autoExecutionAccounts.find((a) => a.id === form.accountId);
  const usdRate = rate && !rate.is_fallback ? rate.usd_krw : null;
  const amount = form.dcaAmountKrw;
  const rows =
    portfolio && amount ? splitDcaAmount(portfolio.items, amount, account?.tax_type, usdRate) : [];
  const totalUsd = rows.reduce((sum, r) => sum + (r.usd ?? 0), 0);
  const tooSmall = amount !== null && amount < DCA_AMOUNT_MIN_KRW;

  return (
    <div>
      <label
        htmlFor="dca-amount"
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
      >
        매회 적립 금액
      </label>
      <div className="flex items-center gap-2">
        <input
          id="dca-amount"
          type="number"
          inputMode="numeric"
          min={DCA_AMOUNT_MIN_KRW}
          step={10_000}
          placeholder="예: 500000 (비우면 예수금 전체)"
          value={amount ?? ""}
          onChange={(e) => {
            const v = e.target.value;
            form.setDcaAmountKrw(v === "" ? null : Math.max(0, Math.floor(Number(v))));
          }}
          className={`w-full ${INPUT_SM}`}
        />
        <span className="text-sm text-gray-500 dark:text-gray-400 shrink-0">원</span>
      </div>
      {tooSmall && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">
          {DCA_AMOUNT_MIN_KRW.toLocaleString()}원 이상 입력해주세요.
        </p>
      )}
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
        {amount
          ? "예수금이 더 많아도 이 금액까지만 목표 비중대로 나눠 매수합니다. 해외 종목은 환전해 둔 달러로 사고, 달러가 모자라면 환전 안내 후 기다렸다가 다시 매수합니다."
          : "비워 두면 지정일에 계좌 예수금 전체로 목표 비중을 채웁니다."}
      </p>
      {rows.length > 0 && (
        <ul className="mt-2 divide-y divide-gray-100 dark:divide-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 text-xs">
          {rows.map((r) => (
            <li key={r.ticker} className="flex items-center justify-between gap-2 px-3 py-1.5">
              <span className="truncate text-gray-700 dark:text-gray-300">{r.name}</span>
              <span className="shrink-0 tabular-nums text-gray-900 dark:text-gray-100">
                {r.amountKrw.toLocaleString()}원
                {r.usd !== null && (
                  <span className="ml-1 text-gray-400 dark:text-gray-500">
                    (≈ ${r.usd.toLocaleString()})
                  </span>
                )}
              </span>
            </li>
          ))}
          {totalUsd > 0 && (
            <li className="px-3 py-1.5 text-amber-700 dark:text-amber-300">
              해외 몫 약 ${totalUsd.toLocaleString(undefined, { maximumFractionDigits: 2 })}를
              매수일 전에 환전해 두세요.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
