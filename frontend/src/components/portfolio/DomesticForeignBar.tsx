import { fmtKrwShort } from "../../utils/format";

interface Item {
  name: string;
  value: number;
  pct: number;
}

interface Props {
  items: Item[];
}

export default function DomesticForeignBar({ items }: Props) {
  const domestic = items.find((i) => i.name === "국내 주식");
  const foreign = items.find((i) => i.name === "해외 주식");

  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">국내/해외 비중</h3>

      {items.length === 0 ? (
        <div className="h-16 flex items-center justify-center text-gray-300 dark:text-gray-600 text-sm">
          데이터 없음
        </div>
      ) : (
        <div className="space-y-4">
          {/* 스택 바 */}
          <div className="flex h-8 rounded-lg overflow-hidden">
            {domestic && (
              <div
                className="bg-indigo-500 flex items-center justify-center text-white text-xs font-medium transition-all"
                style={{ width: `${domestic.pct}%` }}
              >
                {domestic.pct >= 15 ? `${domestic.pct.toFixed(1)}%` : ""}
              </div>
            )}
            {foreign && (
              <div
                className="bg-amber-400 flex items-center justify-center text-white text-xs font-medium transition-all"
                style={{ width: `${foreign.pct}%` }}
              >
                {foreign.pct >= 15 ? `${foreign.pct.toFixed(1)}%` : ""}
              </div>
            )}
          </div>

          {/* 범례 */}
          <div className="flex justify-between gap-2">
            {domestic && (
              <div className="flex items-start gap-2 min-w-0">
                <span className="mt-1 w-3 h-3 rounded-sm bg-indigo-500 shrink-0" />
                <div className="min-w-0">
                  <div className="text-xs text-gray-500 dark:text-gray-400">국내 주식</div>
                  <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                    {domestic.pct.toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500">{fmtKrwShort(domestic.value)}원</div>
                </div>
              </div>
            )}
            {foreign && (
              <div className="flex items-start gap-2 min-w-0 text-right justify-end">
                <div className="min-w-0">
                  <div className="text-xs text-gray-500 dark:text-gray-400">해외 주식</div>
                  <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
                    {foreign.pct.toFixed(1)}%
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500">{fmtKrwShort(foreign.value)}원</div>
                </div>
                <span className="mt-1 w-3 h-3 rounded-sm bg-amber-400 shrink-0" />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
