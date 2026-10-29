import { memo, useState } from "react";
import { PIE_COLORS } from "@/utils/colors";
import { fmtKrwShort } from "@/utils/format";

interface Slice {
  name: string;
  value: number;
  pct: number;
}

interface Props {
  data: Slice[];
  /** 접근성 레이블 접두어 */
  label?: string;
  /** 금액을 숨김 — 조각 툴팁에 이름·비중만 표시(홈 금액 숨김 상태) */
  hideValues?: boolean;
}

// 반지름 25, 두께 15 → 안쪽 17.5 / 바깥 32.5 (viewBox 100 기준) — 예전 recharts 도넛(35%/65%)과 같은 비율
const RADIUS = 25;
const STROKE = 15;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 1.6; // 조각 사이 간격(원주 길이 단위, 약 3도)

/**
 * 의존성 없는 SVG 도넛. 홈 첫 카드에서 이 작은 도넛 하나 때문에 recharts 청크(약 435KB)를 받아
 * 파싱하던 것을 대체한다. 조각을 누르면 가운데에 이름·비중을 보여주고, 금액은 조각 툴팁(<title>)에만 둔다(recharts 툴팁 대체).
 */
export default memo(function MiniDonut({ data, label = "자산 구성", hideValues }: Props) {
  const [active, setActive] = useState<number | null>(null);
  const total = data.reduce((sum, d) => sum + Math.max(d.value, 0), 0);
  if (total <= 0) return null;

  const single = data.filter((d) => d.value > 0).length === 1;
  let offset = 0;
  const segments = data.map((d, i) => {
    const length = (Math.max(d.value, 0) / total) * CIRCUMFERENCE;
    const seg = {
      key: `${d.name}-${i}`,
      datum: d,
      color: PIE_COLORS[i % PIE_COLORS.length],
      dash: single ? length : Math.max(length - GAP, 0),
      offset,
    };
    offset += length;
    return seg;
  });
  const selected = active !== null ? data[active] : null;

  return (
    <svg
      viewBox="0 0 100 100"
      className="w-full h-full"
      role="img"
      aria-label={`${label}: ${data.map((d) => `${d.name} ${d.pct.toFixed(0)}%`).join(", ")}`}
    >
      <g transform="rotate(-90 50 50)">
        {segments.map((s, i) => (
          <circle
            key={s.key}
            cx="50"
            cy="50"
            r={RADIUS}
            fill="none"
            stroke={s.color}
            strokeWidth={active === i ? STROKE + 2 : STROKE}
            strokeDasharray={`${s.dash} ${CIRCUMFERENCE - s.dash}`}
            strokeDashoffset={-s.offset}
            onClick={() => setActive(active === i ? null : i)}
            className="cursor-pointer transition-[stroke-width] duration-150"
          >
            <title>
              {`${s.datum.name} ${s.datum.pct.toFixed(1)}%` +
                (hideValues ? "" : ` (${fmtKrwShort(s.datum.value)}원)`)}
            </title>
          </circle>
        ))}
      </g>
      {selected && (
        <text
          x="50"
          y="50"
          textAnchor="middle"
          className="fill-gray-700 dark:fill-gray-200"
          style={{ fontSize: 7 }}
        >
          <tspan x="50" dy="-2">
            {selected.name}
          </tspan>
          <tspan x="50" dy="8" style={{ fontWeight: 600 }}>
            {selected.pct.toFixed(1)}%
          </tspan>
        </text>
      )}
    </svg>
  );
});
