import { CorrelationResult } from "@/api/backtest";

interface Props {
  result: CorrelationResult;
}

function corrColor(v: number | null): string {
  if (v == null) return "bg-gray-700";
  const t = (v + 1) / 2; // map [-1, 1] → [0, 1]
  const r = Math.round(59 + (239 - 59) * t);   // 59→239 (blue→red)
  const g = Math.round(130 + (68 - 130) * Math.abs(v));  // mid=gray, edges=vivid
  const b = Math.round(246 + (68 - 246) * t);  // 246→68
  return `rgb(${r},${g},${b})`;
}

function textColor(v: number | null): string {
  if (v == null) return "text-gray-500";
  return Math.abs(v) > 0.6 ? "text-white" : "text-gray-800 dark:text-gray-200";
}

export default function CorrelationHeatmap({ result }: Props) {
  const { labels, matrix } = result;

  if (!labels.length || !matrix.length) {
    return (
      <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">
        상관관계 데이터가 없습니다. 선택된 포트폴리오 종목의 가격 데이터가 부족합니다.
      </p>
    );
  }

  const n = labels.length;

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">
        종목 간 상관관계 (월별 수익률 기준)
        <span className="ml-2 text-gray-500 dark:text-gray-600">-1 = 역상관 · 0 = 무관 · +1 = 양의 상관</span>
      </p>
      <div className="overflow-x-auto">
        <div
          className="inline-grid gap-px"
          style={{
            gridTemplateColumns: `minmax(80px, 1fr) repeat(${n}, minmax(52px, 1fr))`,
            minWidth: `${80 + n * 52}px`,
          }}
        >
          {/* 헤더 행: 빈 셀 + 열 레이블 */}
          <div />
          {labels.map((label, j) => (
            <div
              key={j}
              className="text-center text-xs font-medium text-gray-500 dark:text-gray-400 pb-1 px-1 truncate"
              title={label}
            >
              {label.length > 8 ? label.slice(0, 7) + "…" : label}
            </div>
          ))}

          {/* 데이터 행 */}
          {matrix.map((row, i) => (
            <>
              <div
                key={`label-${i}`}
                className="flex items-center text-xs font-medium text-gray-500 dark:text-gray-400 pr-2 truncate"
                title={labels[i]}
              >
                {labels[i].length > 10 ? labels[i].slice(0, 9) + "…" : labels[i]}
              </div>
              {row.map((v, j) => (
                <div
                  key={j}
                  className={`h-10 flex items-center justify-center rounded text-xs font-semibold ${textColor(v)}`}
                  style={{ backgroundColor: corrColor(v) }}
                  title={`${labels[i]} × ${labels[j]}: ${v != null ? v.toFixed(3) : "N/A"}`}
                >
                  {v != null ? v.toFixed(2) : "—"}
                </div>
              ))}
            </>
          ))}
        </div>
      </div>

      {/* 범례 */}
      <div className="flex items-center gap-2 justify-end pt-1">
        <div
          className="h-3 w-24 rounded"
          style={{ background: "linear-gradient(to right, rgb(59,130,246), rgb(229,231,235), rgb(239,68,68))" }}
        />
        <div className="flex items-center justify-between w-24 text-xs text-gray-400">
          <span>-1</span><span>0</span><span>+1</span>
        </div>
      </div>
    </div>
  );
}
