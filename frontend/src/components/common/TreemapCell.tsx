import { PIE_COLORS } from "@/utils/colors";

interface TreemapCellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pct?: number;
  ticker?: string;
  index?: number;
}

export default function TreemapCell({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  name = "",
  pct = 0,
  ticker = "",
  index = 0,
}: TreemapCellProps) {
  const color = PIE_COLORS[index % PIE_COLORS.length];

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} stroke="#fff" strokeWidth={2} rx={3} />
      {width > 50 && height > 30 && (
        <>
          <text x={x + width / 2} y={y + height / 2 - 7} fill="#fff"
            textAnchor="middle" fontSize={12} fontWeight="bold">
            {name.length > 8 ? name.slice(0, 7) + "…" : name}
          </text>
          <text x={x + width / 2} y={y + height / 2 + 9} fill="rgba(255,255,255,0.85)"
            textAnchor="middle" fontSize={11}>
            {pct.toFixed(1)}%
          </text>
          {height > 55 && ticker && (
            <text x={x + width / 2} y={y + height / 2 + 22} fill="rgba(255,255,255,0.6)"
              textAnchor="middle" fontSize={10}>
              {ticker}
            </text>
          )}
        </>
      )}
    </g>
  );
}
