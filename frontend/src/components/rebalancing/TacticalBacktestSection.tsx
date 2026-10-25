import { lazy, Suspense, useMemo, useState } from "react";
import { History } from "lucide-react";
import type { TacticalBacktestResult, TacticalRegime } from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useTacticalBacktest } from "@/hooks/useTacticalAllocation";
import { extractErrorMessage } from "@/utils/error";
import { fmtPct } from "@/utils/format";
import {
  REGIME_BADGE_CLASS,
  REGIME_LABEL,
  TILT_LABEL,
  TILT_ORDER,
  toChartSeries,
} from "./tacticalLabels";

// recharts 청크는 카드를 펼쳐 결과가 왔을 때만 받는다
const BacktestResultChart = lazy(() => import("@/components/backtest/BacktestResultChart"));

const YEAR_OPTIONS = [
  { value: "10", label: "10년" },
  { value: "20", label: "20년" },
] as const;
type YearOption = (typeof YEAR_OPTIONS)[number]["value"];

const REGIME_ORDER: TacticalRegime[] = ["RISK_ON", "NEUTRAL", "RISK_OFF"];
const TIMELINE_PREVIEW = 5;

function RegimeTimeline({ timeline }: { timeline: TacticalBacktestResult["regime_timeline"] }) {
  const [showAll, setShowAll] = useState(false);
  const recentFirst = [...timeline].reverse();
  const shown = showAll ? recentFirst : recentFirst.slice(0, TIMELINE_PREVIEW);
  if (!shown.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-gray-600 dark:text-gray-300">
        최근 국면 전환(백테스트)
      </span>
      <ul className="flex flex-col gap-1 text-xs">
        {shown.map((t) => (
          <li key={`${t.date}-${t.regime}`} className="flex items-center gap-2">
            <span className="tabular-nums text-gray-500 dark:text-gray-400">{t.date}</span>
            <span className={`px-2 py-0.5 rounded-full border ${REGIME_BADGE_CLASS[t.regime]}`}>
              {REGIME_LABEL[t.regime]}
            </span>
          </li>
        ))}
      </ul>
      {recentFirst.length > TIMELINE_PREVIEW && (
        <button
          type="button"
          className="self-start text-xs text-blue-600 dark:text-blue-400"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? "접기" : `더 보기 (${recentFirst.length - TIMELINE_PREVIEW}건)`}
        </button>
      )}
    </div>
  );
}

interface Props {
  portfolioId: string;
}

/** 전술 배분 규칙을 과거 일봉에 재현한 백테스트 — 보조 도구라 기본 접힘(백테스트 카드와 같은 예외). */
export default function TacticalBacktestSection({ portfolioId }: Props) {
  const [isOpen, toggle] = useCollapsible(false, "growlio:rebalancing:tactical-backtest-open");
  const [years, setYears] = useState<YearOption>("10");
  const { data, isLoading, isError, error } = useTacticalBacktest(
    portfolioId,
    Number(years),
    isOpen,
  );
  // 매 렌더 새 배열을 넘기면 memo(BacktestResultChart)가 무력화돼 차트 데이터를 다시 계산한다
  const chart = useMemo(() => (data ? toChartSeries(data) : null), [data]);

  return (
    <CollapsibleCard
      icon={History}
      title="규칙 백테스트"
      isOpen={isOpen}
      onToggle={toggle}
      collapsedHint="이 국면 규칙을 과거에 적용했다면 같은 평균 비중 보유·SPY·QQQ와 어떻게 달랐는지 확인해요"
    >
      <div className="flex flex-col gap-3">
        <SegmentedControl
          options={YEAR_OPTIONS}
          value={years}
          onChange={setYears}
          ariaLabel="백테스트 기간"
        />
        {isLoading && <SkeletonCard rows={3} />}
        {isError && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {extractErrorMessage(error, "백테스트를 불러오지 못했습니다")}
          </p>
        )}
        {data && (
          <>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {data.start_date} ~ {data.end_date} · 국면 전환 {data.regime_switches}회 · 연 회전율{" "}
              {data.turnover_pct_per_year}%
              {data.tilt_shift_pct > 0 &&
                ` · 나스닥·S&P 조절 ${data.tilt_switches}회(${data.tilt_shift_pct}%p)`}
              {(data.dip_shift_pct ?? 0) > 0 &&
                ` · 웅덩이 매수 ${data.dip_entries ?? 0}회(투입 상태 ${data.dip_time_pct ?? 0}%)`}
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 dark:text-gray-400 text-left">
                    <th className="py-1 font-medium">구분</th>
                    <th className="py-1 font-medium text-right">연평균</th>
                    <th className="py-1 font-medium text-right">최대낙폭</th>
                    <th className="py-1 font-medium text-right">샤프</th>
                  </tr>
                </thead>
                <tbody>
                  {data.metrics.map((m, idx) => (
                    <tr
                      key={m.name}
                      className={`border-t border-gray-100 dark:border-gray-700 ${idx === 0 ? "font-semibold" : ""}`}
                    >
                      <td className="py-1.5">{m.name}</td>
                      <td
                        className={`py-1.5 text-right ${m.cagr_pct >= 0 ? "text-red-500" : "text-blue-500"}`}
                      >
                        {fmtPct(m.cagr_pct, 1)}
                      </td>
                      <td className="py-1.5 text-right text-blue-500">-{m.mdd_pct.toFixed(1)}%</td>
                      <td className="py-1.5 text-right">{m.sharpe_ratio.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              &lsquo;평균 비중 고정&rsquo;은 전술 배분이 기간 중 평균적으로 든 비중을 그대로 둔
              결과예요. 전술 배분이 이 줄보다 나아야 국면 판단이 가치를 더한 거예요.
            </p>
            {chart && (
              <Suspense fallback={<SkeletonCard rows={2} />}>
                <BacktestResultChart dates={chart.dates} series={chart.series} />
              </Suspense>
            )}
            <div className="flex flex-wrap gap-2 text-xs text-gray-600 dark:text-gray-300">
              {REGIME_ORDER.map((r) => (
                <span key={r} className="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700">
                  {REGIME_LABEL[r]} {data.regime_time_pct[r]}%
                </span>
              ))}
              {data.tilt_shift_pct > 0 &&
                TILT_ORDER.map((t) => (
                  <span key={t} className="px-2 py-0.5 rounded-full bg-gray-50 dark:bg-gray-800">
                    {TILT_LABEL[t]} {data.tilt_time_pct[t]}%
                  </span>
                ))}
            </div>
            <RegimeTimeline timeline={data.regime_timeline} />
            <ul className="text-xs text-gray-500 dark:text-gray-400 list-disc pl-4 space-y-0.5">
              <li>{data.macro_note}</li>
              <li>{data.assumptions}</li>
              <li>과거 성과가 미래 수익을 보장하지 않습니다.</li>
            </ul>
          </>
        )}
      </div>
    </CollapsibleCard>
  );
}
