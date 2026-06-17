// 차트/트리맵 팔레트
export const PIE_COLORS = [
  "#2563EB",
  "#16A34A",
  "#D97706",
  "#DC2626",
  "#7C3AED",
  "#0891B2",
  "#DB2777",
  "#EA580C",
  "#65A30D",
  "#0284C7",
  "#9333EA",
  "#475569",
];

// 한국 주식 관례: 수익=빨강, 손실=파랑
export const PROFIT_COLOR = "text-red-500";
export const LOSS_COLOR = "text-blue-500";

/** 수익/손실 여부에 따른 Tailwind 클래스 반환 */
export function pnlColor(value: number): string {
  return value >= 0 ? PROFIT_COLOR : LOSS_COLOR;
}
