import { useQuery } from "@tanstack/react-query";
import { fetchAccountPositions } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

interface Position {
  ticker: string;
  name: string;
  qty: number;
}

export function useAccountPositions(accountId: string, enabled: boolean) {
  const { data } = useQuery<{ positions: Position[] }>({
    queryKey: QUERY_KEYS.accountPositions(accountId),
    queryFn: () => fetchAccountPositions<Position>(accountId),
    enabled: enabled && !!accountId,
    staleTime: STALE_TIME.MEDIUM,
  });
  return data?.positions ?? [];
}
