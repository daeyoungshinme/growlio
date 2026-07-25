import { useQuery } from "@tanstack/react-query";
import { fetchPensionContribution } from "@/api/tax";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import type { PortfolioOverview } from "@/types";
import { fmtKrw } from "@/utils/format";

function achievementColor(pct: number): string {
  if (pct >= 100) return "text-green-600 dark:text-green-400";
  if (pct >= 50) return "text-blue-600 dark:text-blue-400";
  return "text-gray-500 dark:text-gray-400";
}

interface Props {
  overview: PortfolioOverview | undefined;
}

/** 연금저축(600만원)+IRP(합산 900만원) 소득공제 한도 대비 올해 납입 진행률을 보여준다.
 * 연금저축/IRP로 태그된 계좌가 없으면 표시하지 않는다. `TaxLimitsSection`(`TaxTabContainer`의
 * "한도 현황" 탭)이 렌더하므로 이 컴포넌트는 헤더/보더 없이 본문만 그린다. */
export default function PensionContributionCard({ overview }: Props) {
  const accounts = overview?.accounts ?? [];
  const hasPensionAccount = accounts.some(
    (a) => a.tax_type === "PENSION_SAVINGS" || a.tax_type === "IRP",
  );

  const currentYear = new Date().getFullYear();
  const { data } = useQuery({
    queryKey: QUERY_KEYS.pensionContribution(currentYear),
    queryFn: () => fetchPensionContribution(currentYear),
    staleTime: STALE_TIME.MEDIUM,
    enabled: hasPensionAccount,
  });

  if (!hasPensionAccount || !data) return null;

  const chips = [
    {
      key: "pension_savings",
      label: "연금저축",
      current: data.pension_savings_deposit_krw,
      limit: data.pension_savings_limit_krw,
      pct: data.pension_savings_achievement_pct,
      barColorClass: "bg-blue-500",
    },
    {
      key: "total",
      label: "합산 한도 (연금저축+IRP)",
      current: data.total_deposit_krw,
      limit: data.total_limit_krw,
      pct: data.total_achievement_pct,
      barColorClass: "bg-emerald-500",
    },
  ];

  return (
    <div>
      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase mb-1.5">
        연금저축·IRP 납입 현황 ({data.year}년)
      </p>
      <div className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700">
        {chips.map((chip) => (
          <div key={chip.key} className="min-w-0 bg-white dark:bg-gray-900 p-2">
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 truncate">{chip.label}</p>
            <span className={`text-sm font-bold ${achievementColor(chip.pct)}`}>
              {Math.min(chip.pct, 999).toFixed(1)}%
            </span>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {fmtKrw(chip.current)} / {fmtKrw(chip.limit)}
            </p>
            <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
              <div
                className={`h-full rounded-full ${chip.barColorClass}`}
                style={{ width: `${Math.min(Math.max(chip.pct, 0), 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">{data.note}</p>
    </div>
  );
}
