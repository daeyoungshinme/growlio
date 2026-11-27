import { useQuery } from "@tanstack/react-query";
import { fetchUsdKrwOn } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { localToday } from "@/utils/format";

export interface TradeDateUsdRate {
  /** 환산에 쓸 환율 — 아직 모르면 null */
  rate: number | null;
  /** 화면 안내 — "2026-05-08 종가 환율" / "현재 환율" / "거래일 환율을 못 받아 현재 환율" */
  basis: string;
  loading: boolean;
}

/**
 * 수기 해외 거래 단가(USD)를 원화로 환산할 환율 — 지난 거래일이면 그날(휴일이면 직전 거래일) 종가, 오늘이면 현재 환율.
 * 오늘 환율로 고정하면 지난 거래를 나중에 적을 때 그 사이 환율 변동만큼 해외 양도세 실현손익이 틀어졌다(plans/156).
 * 거래일 종가를 못 받으면 현재 환율로 대신하고 basis로 알린다.
 */
export function useTradeDateUsdRate(
  tradeDate: string,
  enabled: boolean,
  liveRate: number | null | undefined,
): TradeDateUsdRate {
  const isPast = !!tradeDate && tradeDate < localToday();
  const query = useQuery({
    queryKey: QUERY_KEYS.usdKrwOn(tradeDate),
    queryFn: () => fetchUsdKrwOn(tradeDate),
    enabled: enabled && isPast,
    // 지난 날짜 종가는 바뀌지 않는다
    staleTime: Infinity,
  });
  const live = liveRate || null;

  if (!enabled || !isPast) return { rate: live, basis: "현재 환율", loading: false };
  if (query.isPending) return { rate: null, basis: "거래일 환율 확인 중", loading: true };
  const historical = query.data?.usd_krw;
  if (historical && query.data?.rate_date) {
    return { rate: historical, basis: `${query.data.rate_date} 종가 환율`, loading: false };
  }
  return { rate: live, basis: "거래일 환율을 못 받아 현재 환율", loading: false };
}
