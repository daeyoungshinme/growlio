import { lazy, Suspense, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Info, Plus } from "lucide-react";
import EmptyState from "@/components/common/EmptyState";
import SkeletonCard from "@/components/common/SkeletonCard";
import type { AssetAccount } from "@/api/assets";
import {
  fetchPeriodPurchases,
  type PeriodPurchaseItem,
  type PeriodPurchaseSummary,
  type PeriodType,
} from "@/api/trades";
import type { TradePrefill } from "./TradeFormModal";
import { STOCK_TYPES } from "@/constants";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY, TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { fmtKrw, fmtKrwPrice, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";

const TradeFormModal = lazy(() => import("./TradeFormModal"));

interface Props {
  accounts: AssetAccount[];
}

const PERIOD_OPTIONS: { value: PeriodType; label: string }[] = [
  { value: "month", label: "월간" },
  { value: "year", label: "연간" },
];

function shiftPeriod(period: PeriodType, year: number, month: number, step: number) {
  if (period === "year") return { year: year + step, month };
  const idx = year * 12 + (month - 1) + step;
  return { year: Math.floor(idx / 12), month: (idx % 12) + 1 };
}

export default function PeriodPurchasesTab({ accounts }: Props) {
  const now = new Date();
  const thisYear = now.getFullYear();
  const thisMonth = now.getMonth() + 1;
  const [period, setPeriod] = useState<PeriodType>("month");
  const [year, setYear] = useState(thisYear);
  const [month, setMonth] = useState(thisMonth);
  const [accountId, setAccountId] = useState("");
  const [modal, setModal] = useState<{ prefill: TradePrefill | null } | null>(null);

  const stockAccounts = useMemo(
    () => accounts.filter((a) => STOCK_TYPES.includes(a.asset_type)),
    [accounts],
  );

  const monthParam = period === "month" ? month : null;
  const { data, isLoading, isError } = useQuery<PeriodPurchaseSummary>({
    queryKey: QUERY_KEYS.periodPurchases(period, year, monthParam, accountId || null),
    queryFn: () =>
      fetchPeriodPurchases({
        period,
        year,
        month: monthParam ?? undefined,
        account_id: accountId || undefined,
      }),
    staleTime: STALE_TIME.MEDIUM,
  });

  const isCurrent =
    period === "year" ? year >= thisYear : year * 12 + month >= thisYear * 12 + thisMonth;
  const periodLabel = period === "year" ? `${year}년` : `${year}년 ${month}월`;
  const move = (step: number) => {
    const next = shiftPeriod(period, year, month, step);
    setYear(next.year);
    setMonth(next.month);
  };
  const changePeriod = (next: PeriodType) => {
    setPeriod(next);
    if (next === "month" && year === thisYear) setMonth(thisMonth);
  };

  const summary = data?.summary;
  const items = data?.items ?? [];
  const hasEstimated = items.some((i) => i.source === "ESTIMATED");

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5" role="group" aria-label="기간 단위">
            {PERIOD_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                aria-pressed={period === o.value}
                onClick={() => changePeriod(o.value)}
                className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                  period === o.value
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
          <div className="flex items-center ml-auto sm:ml-2">
            <button
              type="button"
              onClick={() => move(-1)}
              aria-label="이전 기간"
              className={`${TOUCH_TARGET_MIN} rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800`}
            >
              <ChevronLeft size={18} />
            </button>
            <span className="min-w-[96px] text-center text-sm font-semibold text-gray-900 dark:text-gray-50">
              {periodLabel}
            </span>
            <button
              type="button"
              onClick={() => move(1)}
              disabled={isCurrent}
              aria-label="다음 기간"
              className={`${TOUCH_TARGET_MIN} rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30`}
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
        <select
          value={accountId}
          onChange={(e) => setAccountId(e.target.value)}
          aria-label="계좌 필터"
          className={`${INPUT_SM} w-full sm:w-auto min-w-0`}
        >
          <option value="">전체 증권계좌</option>
          {stockAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setModal({ prefill: null })}
          disabled={stockAccounts.length === 0}
          className={`${TOUCH_TARGET_MIN} sm:ml-auto gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          <Plus size={16} />
          매매 기록 추가
        </button>
      </div>

      {isLoading ? (
        <SkeletonCard rows={3} />
      ) : isError || !data || !summary ? (
        <div className="card">
          <EmptyState title="기간별 매수 현황을 불러오지 못했습니다." compact />
        </div>
      ) : (
        <>
          <div className="card">
            <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {periodLabel} 매수 종목 수익
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Stat label="매수 금액" value={fmtKrw(summary.bought_amount_krw)} />
              <Stat label="현재 평가금액" value={fmtKrw(summary.value_krw)} />
              <Stat
                label="손익"
                value={fmtKrw(summary.total_pnl_krw)}
                className={pnlColor(summary.total_pnl_krw)}
                sub={
                  summary.realized_pnl_krw !== 0
                    ? `실현 ${fmtKrw(summary.realized_pnl_krw)} 포함`
                    : undefined
                }
              />
              <Stat
                label="수익률"
                value={fmtPct(summary.return_pct)}
                className={summary.return_pct != null ? pnlColor(summary.return_pct) : undefined}
              />
            </div>
          </div>

          {(hasEstimated || data.tracking_started.length > 0) && (
            <div className="flex gap-2 rounded-xl bg-gray-50 dark:bg-gray-800/60 p-3 text-xs text-gray-500 dark:text-gray-400">
              <Info size={14} className="shrink-0 mt-0.5" />
              <div className="space-y-1">
                {hasEstimated && (
                  <p>
                    <b className="font-medium">추정</b> 항목은 매일 저장되는 보유 수량·평단 변화로
                    계산한 값입니다. 같은 날 사고판 거래나 동기화가 없던 날의 매매는 반영되지 않을
                    수 있어요. 정확히 보려면 매매를 직접 기록하세요.
                  </p>
                )}
                {data.tracking_started.map((t) => (
                  <p key={t.account_id}>
                    {t.account_name}: {t.since} 이전 기록이 없어 그날 보유분은 기존 보유로 봤어요.
                  </p>
                ))}
              </div>
            </div>
          )}

          {items.length === 0 ? (
            <div className="card">
              <EmptyState title={`${periodLabel}에 매수한 종목이 없습니다.`} compact />
            </div>
          ) : (
            <ul className="space-y-3">
              {items.map((item) => (
                <PurchaseRow
                  key={`${item.account_id}-${item.ticker}-${item.market}`}
                  item={item}
                  showAccount={!accountId && stockAccounts.length > 1}
                  onRecord={() =>
                    setModal({
                      prefill: {
                        account_id: item.account_id,
                        ticker: item.ticker,
                        market: item.market,
                        name: item.name,
                      },
                    })
                  }
                />
              ))}
            </ul>
          )}
        </>
      )}

      {modal && (
        <Suspense fallback={null}>
          <TradeFormModal
            accounts={stockAccounts}
            prefill={modal.prefill}
            onClose={() => setModal(null)}
          />
        </Suspense>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  className,
  sub,
}: {
  label: string;
  value: string;
  className?: string;
  sub?: string;
}) {
  return (
    <div>
      <p className="text-xs text-gray-500 dark:text-gray-400">{label}</p>
      <p className={`text-base font-bold mt-0.5 ${className ?? "text-gray-900 dark:text-gray-50"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
    </div>
  );
}

function PurchaseRow({
  item,
  showAccount,
  onRecord,
}: {
  item: PeriodPurchaseItem;
  showAccount: boolean;
  onRecord: () => void;
}) {
  const manual = item.source === "MANUAL";
  return (
    <li className="card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">
              {item.name || item.ticker}
            </span>
            <span
              className={`px-1.5 py-0.5 rounded text-xs ${
                manual
                  ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                  : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
              }`}
            >
              {manual ? "기록" : "추정"}
            </span>
            {item.partially_sold && (
              <span className="px-1.5 py-0.5 rounded text-xs bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                {item.held_qty > 0 ? "일부 매도" : "전량 매도"}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {item.ticker} · {item.market}
            {showAccount && ` · ${item.account_name}`}
            {item.first_buy_date && ` · 첫 매수 ${item.first_buy_date}`}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p
            className={`text-sm font-bold ${item.return_pct != null ? pnlColor(item.return_pct) : ""}`}
          >
            {fmtPct(item.return_pct)}
          </p>
          <p className={`text-xs ${pnlColor(item.total_pnl_krw)}`}>{fmtKrw(item.total_pnl_krw)}</p>
        </div>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <dt className="text-gray-500 dark:text-gray-400">매수</dt>
        <dd className="text-right text-gray-900 dark:text-gray-50">
          {item.bought_qty.toLocaleString()}주 × {fmtKrwPrice(item.avg_buy_price_krw)}
          {item.price_estimated && " (추정)"}
        </dd>
        <dt className="text-gray-500 dark:text-gray-400">매수 금액</dt>
        <dd className="text-right text-gray-900 dark:text-gray-50">
          {fmtKrw(item.bought_amount_krw)}
        </dd>
        {item.held_qty > 0 && (
          <>
            <dt className="text-gray-500 dark:text-gray-400">현재 보유</dt>
            <dd className="text-right text-gray-900 dark:text-gray-50">
              {item.held_qty.toLocaleString()}주
              {item.current_price_krw != null && ` × ${fmtKrwPrice(item.current_price_krw)}`}
            </dd>
          </>
        )}
        {item.realized_pnl_krw !== 0 && (
          <>
            <dt className="text-gray-500 dark:text-gray-400">실현 손익</dt>
            <dd className={`text-right ${pnlColor(item.realized_pnl_krw)}`}>
              {fmtKrw(item.realized_pnl_krw)}
            </dd>
          </>
        )}
      </dl>
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={onRecord}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline`}
        >
          {manual ? "기록 보기·추가" : "직접 기록하기"}
        </button>
      </div>
    </li>
  );
}
