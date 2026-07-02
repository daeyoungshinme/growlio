import { fmtKrwPrice } from "@/utils/format";

interface PriceCellProps {
  krw: number | null | undefined;
  usd?: number | null;
  isOverseas?: boolean;
  className?: string;
}

/**
 * 해외/국내 종목 가격 표시 셀.
 * 해외 종목(isOverseas=true)이고 usd 값이 있으면 USD 주표시 + KRW 보조.
 * 국내 종목이면 KRW 원 단위 표시.
 */
export default function PriceCell({
  krw,
  usd,
  isOverseas = false,
  className = "",
}: PriceCellProps) {
  const textClass = `text-sm font-medium text-gray-700 dark:text-gray-300 ${className}`;

  if (isOverseas && usd) {
    return (
      <div>
        <p className={textClass}>${usd.toFixed(2)}</p>
        {(krw ?? 0) > 0 && (
          <p className="text-xs text-gray-400 dark:text-gray-500">₩{(krw ?? 0).toLocaleString()}</p>
        )}
      </div>
    );
  }

  return <span className={textClass}>{fmtKrwPrice(krw ?? 0)}</span>;
}
