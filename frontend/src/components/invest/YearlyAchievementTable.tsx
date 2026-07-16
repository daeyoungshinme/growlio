import type { YearlyAchievement } from "@/api/invest";
import AchievementTable from "./AchievementTable";

interface Props {
  data: YearlyAchievement[];
  flat?: boolean;
}

export default function YearlyAchievementTable({ data, flat }: Props) {
  const rows = data
    .filter((d) => d.has_data)
    .map((d) => ({
      key: String(d.year),
      label: `${d.year}년`,
      projected: d.projected_year_end_krw,
      actual: d.actual_year_end_krw,
      achievementPct: d.achievement_pct,
    }));

  return (
    <AchievementTable
      title="연별 계획 대비 달성율"
      subtitle="이론값(복리 계획 곡선) 대비 실제 자산 비율입니다"
      emptyTitle="스냅샷 데이터가 없습니다."
      projectedLabel="이론 연말값"
      actualLabel="실제 연말값"
      rows={rows}
      flat={flat}
    />
  );
}
