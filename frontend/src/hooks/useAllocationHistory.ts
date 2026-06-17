import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllocationHistory } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export function useAllocationHistory(months = 12) {
  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.allocationHistory(months),
    queryFn: () => fetchAllocationHistory(months),
    staleTime: STALE_TIME.LONG,
    gcTime: STALE_TIME.LONG,
  });

  const { chartData, allTypes } = useMemo(() => {
    if (!data || data.length === 0) return { chartData: [], allTypes: [] as string[] };
    const typeSet = new Set<string>();
    data.forEach((point) => point.allocations.forEach((a) => typeSet.add(a.asset_type)));
    const types = Array.from(typeSet);
    const points = data.map((point) => {
      const entry: Record<string, unknown> = { month: point.month.slice(2, 7).replace("-", ".") };
      const byType = Object.fromEntries(point.allocations.map((a) => [a.asset_type, a.amount_krw]));
      types.forEach((t) => {
        entry[t] = byType[t] ?? 0;
      });
      return entry;
    });
    return { chartData: points, allTypes: types };
  }, [data]);

  const labelMap = useMemo(() => {
    if (!data || data.length === 0) return {} as Record<string, string>;
    const map: Record<string, string> = {};
    data.forEach((point) =>
      point.allocations.forEach((a) => {
        map[a.asset_type] = a.label;
      }),
    );
    return map;
  }, [data]);

  const reversedMonthly = useMemo(() => (data ? [...data].reverse() : []), [data]);

  return { isLoading, chartData, allTypes, labelMap, reversedMonthly };
}
