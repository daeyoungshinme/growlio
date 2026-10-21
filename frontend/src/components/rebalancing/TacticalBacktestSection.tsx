import { useState } from "react";
import { History } from "lucide-react";
import type { TacticalRegime } from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useTacticalBacktest } from "@/hooks/useTacticalAllocation";
import { extractErrorMessage } from "@/utils/error";
import { fmtPct } from "@/utils/format";
import { REGIME_LABEL, TILT_LABEL, TILT_ORDER } from "./tacticalLabels";

const YEAR_OPTIONS = [
  { value: "10", label: "10년" },
  { value: "20", label: "20년" },
] as const;
type YearOption = (typeof YEAR_OPTIONS)[number]["value"];

const REGIME_ORDER: TacticalRegime[] = ["RISK_ON", "NEUTRAL", "RISK_OFF"];

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

  return (
    <CollapsibleCard
      icon={History}
      title="규칙 백테스트"
      isOpen={isOpen}
      onToggle={toggle}
      collapsedHint="이 국면 규칙을 과거에 적용했다면 SPY·QQQ·DIA 단순 보유와 어떻게 달랐는지 확인해요"
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
              {data.start_date} ~ {data.end_date} · 국면 전환 {data.regime_switches}회
              {data.tilt_shift_pct > 0 &&
                ` · 나스닥·S&P 조절 ${data.tilt_switches}회(${data.tilt_shift_pct}%p)`}
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
