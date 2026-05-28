import { PIE_COLORS } from "../../utils/colors";

export default function TreemapCell(props: Record<string, unknown>) {
  const x = (props.x as number) ?? 0;
  const y = (props.y as number) ?? 0;
  const width = (props.width as number) ?? 0;
  const height = (props.height as number) ?? 0;
  const name = (props.name as string) ?? "";
  const pct = (props.pct as number) ?? 0;
  const ticker = (props.ticker as string) ?? "";
  const index = (props.index as number) ?? 0;
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
