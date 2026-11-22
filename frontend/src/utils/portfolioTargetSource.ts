import type { Portfolio, PortfolioTargetSource } from "@/api/portfolios";

const SOURCE_LABEL: Record<PortfolioTargetSource, string> = {
  MANUAL: "직접 입력",
  RECOMMENDATION: "추천 적용",
  TACTICAL: "전술 적용",
};

/** 포트폴리오 카드의 목표 비중 출처 한 줄(plans/145) — "목표: 추천 적용 · 11.20". 기록 이전이면 null. */
export function targetSourceLabel(
  p: Pick<Portfolio, "target_source" | "target_source_at">,
): string | null {
  if (!p.target_source) return null;
  const label = SOURCE_LABEL[p.target_source];
  if (!p.target_source_at) return `목표: ${label}`;
  const d = new Date(p.target_source_at);
  if (Number.isNaN(d.getTime())) return `목표: ${label}`;
  // 로컬(KST) 날짜 — toISOString()은 UTC라 09시 전이면 전날로 보인다
  return `목표: ${label} · ${d.getMonth() + 1}.${d.getDate()}`;
}
