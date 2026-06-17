import { useQuery } from "@tanstack/react-query";
import { fetchDartDisclosures } from "@/api/dart";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { getHttpStatus } from "@/utils/error";

export function useDartDisclosures(days: number) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: QUERY_KEYS.dartDisclosures(days),
    queryFn: () => fetchDartDisclosures(days),
    staleTime: STALE_TIME.LONG,
    retry: false,
  });

  const isDartKeyMissing = isError && getHttpStatus(error) === 422;

  return { data, isLoading, isError, isDartKeyMissing };
}
