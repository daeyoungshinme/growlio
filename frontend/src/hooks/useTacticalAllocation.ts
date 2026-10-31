import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyTacticalWeights,
  deleteTacticalStrategy,
  fetchTacticalBacktest,
  fetchTacticalStatus,
  type TacticalStrategyPayload,
  upsertTacticalStrategy,
} from "@/api/tactical";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { extractErrorMessage } from "@/utils/error";
import { invalidateTacticalData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";

/** 포트폴리오의 전술 배분 국면·차트 지표·제안 비중. 일봉 기준이라 자주 바뀌지 않는다. */
export function useTacticalStatus(portfolioId: string | undefined) {
  return useQuery({
    queryKey: QUERY_KEYS.tacticalStatus(portfolioId ?? ""),
    queryFn: () => fetchTacticalStatus(portfolioId as string),
    enabled: !!portfolioId,
    staleTime: STALE_TIME.MEDIUM,
  });
}

/** 전술 배분 규칙 백테스트 — 카드를 펼쳤을 때만 조회(`enabled`). */
export function useTacticalBacktest(
  portfolioId: string | undefined,
  years: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: QUERY_KEYS.tacticalBacktest(portfolioId ?? "", years),
    queryFn: () => fetchTacticalBacktest(portfolioId as string, years),
    enabled: !!portfolioId && enabled,
    staleTime: STALE_TIME.LONG,
    retry: false,
  });
}

/** 전략 켜기/설정 변경·끄기·제안 비중 적용 뮤테이션 묶음. */
export function useTacticalMutations(portfolioId: string) {
  const queryClient = useQueryClient();

  const upsert = useMutation({
    mutationFn: (payload: TacticalStrategyPayload) => upsertTacticalStrategy(portfolioId, payload),
    onSuccess: async () => {
      await invalidateTacticalData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  /** 인자 dcaLinked — 안내 문구만 고른다. 서버는 적립식 여부와 상관없이 TACTICAL 알림을 모두 일반 모드로 되돌리므로
   * 알림 캐시는 항상 갱신한다(plans/101 A1 — 일부만 연동된 경우 무효화가 빠졌다) */
  const disable = useMutation({
    mutationFn: (_opts?: { dcaLinked?: boolean }) => deleteTacticalStrategy(portfolioId),
    onSuccess: async (_data, opts) => {
      toast(
        opts?.dcaLinked
          ? "전술 배분을 껐습니다. 전술 연동 자동매수는 일반 모드로 바뀌었어요."
          : "전술 배분을 껐습니다. 포트폴리오 목표 비중은 그대로 유지됩니다.",
        "info",
      );
      await invalidateTacticalData(queryClient, { alertsReset: true });
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  /** 인자 fraction(기본 1) — 0.5면 절반만 적용(분할 적용) */
  const apply = useMutation({
    mutationFn: (fraction?: number) => applyTacticalWeights(portfolioId, fraction ?? 1),
    onSuccess: async (_data, fraction) => {
      toast(
        (fraction ?? 1) < 1
          ? "제안 비중의 절반을 목표 비중에 반영했습니다. 나머지는 다음 거래일에 다시 적용하세요"
          : "제안 비중을 목표 비중으로 저장했습니다",
        "success",
      );
      await invalidateTacticalData(queryClient, { portfolioChanged: true });
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return { upsert, disable, apply };
}
