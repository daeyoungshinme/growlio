import type { ReactNode } from "react";

/** 추천 탭 공통 — 설정이 없어 추천을 못 낼 때 안내 문구 + 설정 유도 액션(링크/버튼). */
export function RecommendationSetupCta({
  note,
  fallback,
  action,
}: {
  note: string | null | undefined;
  fallback: string;
  action: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-xs text-gray-500 dark:text-gray-400">{note ?? fallback}</p>
      {action}
    </div>
  );
}

/** 추천 탭 공통 — 설정은 있지만 추천 종목이 비었을 때(후보 부족·최적화 실패) 안내 문구. */
export function RecommendationNoItems({
  note,
  fallback = "추천을 계산할 수 없습니다 — 후보 ETF를 등록해주세요",
}: {
  note: string | null | undefined;
  fallback?: string;
}) {
  return <p className="text-xs text-gray-500 dark:text-gray-400">{note ?? fallback}</p>;
}
