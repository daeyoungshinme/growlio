import type { DCAProjectionPoint } from "@/api/invest";
import AchievementTable from "./AchievementTable";

interface Props {
  data: DCAProjectionPoint[];
  flat?: boolean;
}

export default function MonthlyAchievementTable({ data, flat }: Props) {
  const today = new Date().toISOString().slice(0, 7);
  const rows = data
    .filter((d) => d.month <= today && d.has_data)
    .slice(-24)
    .map((d) => ({
      key: d.month,
      label: d.month,
      projected: d.projected_krw,
      actual: d.actual_krw,
      achievementPct: d.achievement_pct,
    }));

  return (
    <AchievementTable
      title="월별 계획 대비 달성율 (최근 24개월)"
      subtitle="이론값(복리 계획 곡선) 대비 실제 자산 비율입니다"
      emptyTitle="스냅샷 데이터가 없습니다."
      projectedLabel="이론값"
      actualLabel="실제값"
      rows={rows}
      flat={flat}
      scrollable
    />
  );
}
