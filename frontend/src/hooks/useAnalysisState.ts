import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { analyzePortfolio, fetchBrokerBalance, type RebalancingAnalysis } from "@/api/rebalancing";
import { isBrokerBalanceAccount } from "@/utils/accounts";
import { extractErrorMessage } from "@/utils/error";

type AnalysisMode = "rebalancing" | "strategy";

interface AnalysisState {
  mode: AnalysisMode | null;
  analysis: RebalancingAnalysis | null;
  analyzing: boolean;
  error: string | null;
  /** 예수금이 증권사 실시간 잔고 기준인지(false면 마지막 동기화 시점 DB 값) */
  cashIsLive: boolean;
}

const INITIAL_STATE: AnalysisState = {
  mode: null,
  analysis: null,
  analyzing: false,
  error: null,
  cashIsLive: false,
};

/**
 * 증권사 계좌들의 실시간 예수금 합계 — 하나도 조회되지 않으면 undefined(서버가 동기화 시점 DB 값 사용).
 * "실시간 잔고로 다시 분석"(`triggerRebalancingAnalysis(id, { live: true })`)에서만 쓴다 — 예전엔 탭 진입마다
 * 계좌 수만큼 증권사 API를 호출해 분석이 그만큼 늦게 떴다(plans/72 2-5).
 */
async function fetchLiveDepositKrw(accounts: AssetAccount[]): Promise<number | undefined> {
  const brokerAccounts = accounts.filter((a) => isBrokerBalanceAccount(a.asset_type));
  if (brokerAccounts.length === 0) return undefined;
  const results = await Promise.allSettled(brokerAccounts.map((a) => fetchBrokerBalance(a.id)));
  let total = 0;
  let hasSuccess = false;
  for (const r of results) {
    if (r.status === "fulfilled" && !r.value.error) {
      total += r.value.deposit_krw ?? 0;
      hasSuccess = true;
    }
  }
  return hasSuccess ? total : undefined;
}

// ─── 분석 결과 캐시 ──────────────────────────────────────────────────────────
// 포트폴리오 탭에 들어올 때마다 자동 분석(analyze POST)을 다시 돌려 탭을 오갈 때마다 같은 계산을 기다렸다.
// 자동 분석은 최근 결과를 재사용하고, 사용자가 직접 누른 분석만 새로 계산한다.
// 보유·계좌·포트폴리오 데이터가 무효화되면(sync·주문 실행·계좌 수정) 캐시를 비운다.
const ANALYSIS_CACHE_TTL_MS = 5 * 60 * 1000;
const INVALIDATING_PREFIXES = new Set<string>([
  QUERY_KEYS.accounts[0],
  QUERY_KEYS.portfolioOverviewBase[0],
  QUERY_KEYS.portfolios[0],
]);

interface CachedAnalysis {
  analysis: RebalancingAnalysis;
  cashIsLive: boolean;
  signature: string | undefined;
  at: number;
}

const analysisCache = new Map<string, CachedAnalysis>();
const watchedClients = new WeakSet<QueryClient>();

function watchInvalidations(queryClient: QueryClient) {
  if (watchedClients.has(queryClient)) return;
  watchedClients.add(queryClient);
  // 패널이 언마운트된 동안의 무효화도 놓치지 않도록 앱 수명 동안 구독한다
  queryClient.getQueryCache().subscribe((event) => {
    if (
      event.type === "updated" &&
      event.action.type === "invalidate" &&
      INVALIDATING_PREFIXES.has(String(event.query.queryKey[0]))
    ) {
      analysisCache.clear();
    }
  });
}

function readCachedAnalysis(id: string, signature: string | undefined): CachedAnalysis | null {
  const hit = analysisCache.get(id);
  if (!hit) return null;
  if (Date.now() - hit.at > ANALYSIS_CACHE_TTL_MS || hit.signature !== signature) {
    analysisCache.delete(id);
    return null;
  }
  return hit;
}

/** 테스트 격리용 */
export function clearAnalysisCache() {
  analysisCache.clear();
}

export interface TriggerAnalysisOptions {
  /** 증권사 실시간 잔고(예수금)로 분석 — 계좌 수만큼 증권사 API를 호출하므로 사용자가 요청할 때만 */
  live?: boolean;
}

export function useAnalysisState({
  autoAnalyzeId,
  selectedIdStr,
  portfolioItemsSignature,
  getDepositAccounts,
  accountsReady = true,
}: {
  autoAnalyzeId?: string;
  selectedIdStr: string;
  /** 분석 대상 포트폴리오의 목표 비중(items) 직렬화 값 — 값이 바뀌면(저장으로 비중 변경) 자동 재분석 트리거 */
  portfolioItemsSignature?: string;
  /** 포트폴리오의 예수금 기준 계좌 — 실시간 예수금 조회 대상 */
  getDepositAccounts?: (portfolioId: string) => AssetAccount[];
  /** 계좌 목록 로딩 완료 여부 — 자동 분석이 계좌 로딩 전에 돌면 실시간 예수금 없이 분석된다 */
  accountsReady?: boolean;
}) {
  const queryClient = useQueryClient();
  watchInvalidations(queryClient);
  const [state, setState] = useState<AnalysisState>(INITIAL_STATE);
  const autoAnalyzedRef = useRef<string | undefined>(undefined);

  // 마지막으로 분석을 요청한 시점의 비중 시그니처 — 이후 값이 달라지면 재분석이 필요하다는 신호
  const signatureRef = useRef(portfolioItemsSignature);
  signatureRef.current = portfolioItemsSignature;
  const analyzedSignatureRef = useRef<string | undefined>(undefined);
  // 마지막 요청만 반영한다 — 포트폴리오를 빠르게 바꾸면 늦게 도착한 이전 응답이 새 포트폴리오 화면을
  // 덮어써 다른 포트폴리오의 분석이 보였다(plans/62 B5)
  const requestSeqRef = useRef(0);
  const getDepositAccountsRef = useRef(getDepositAccounts);
  getDepositAccountsRef.current = getDepositAccounts;

  const triggerRebalancingAnalysis = useCallback(
    async (id: string, opts?: TriggerAnalysisOptions) => {
      const live = opts?.live ?? false;
      const seq = ++requestSeqRef.current;
      analyzedSignatureRef.current = signatureRef.current;
      // 재분석 시 이전 결과(analysis)를 유지한 채 analyzing만 세워 화면이 비는 깜빡임을 방지
      setState((s) => ({
        ...s,
        mode: "rebalancing",
        analysis: s.mode === "rebalancing" ? s.analysis : null,
        analyzing: true,
        error: null,
      }));
      try {
        // 기본은 마지막 동기화 시점 예수금 — 모든 자동 경로가 같은 기준이라 경로별로 예수금이 달라지지 않는다
        // (plans/63 P1-1). 주문 실행 단계는 실행 패널이 실시간 잔고를 따로 조회한다.
        const depositKrwOverride = live
          ? await fetchLiveDepositKrw(getDepositAccountsRef.current?.(id) ?? [])
          : undefined;
        if (seq !== requestSeqRef.current) return;
        const result = await analyzePortfolio(id, undefined, depositKrwOverride);
        if (seq !== requestSeqRef.current) return;
        const cashIsLive = depositKrwOverride !== undefined;
        analysisCache.set(id, {
          analysis: result,
          cashIsLive,
          signature: analyzedSignatureRef.current,
          at: Date.now(),
        });
        setState((s) => ({
          ...s,
          analysis: result,
          analyzing: false,
          cashIsLive,
        }));
      } catch (err) {
        if (seq !== requestSeqRef.current) return;
        setState((s) => ({
          ...s,
          error: extractErrorMessage(err, "분석 중 오류가 발생했습니다."),
          analyzing: false,
        }));
      }
    },
    [],
  );

  const setMode = useCallback((mode: AnalysisMode) => {
    setState((s) => ({ ...s, mode, analysis: null, error: null }));
  }, []);

  useEffect(() => {
    setState((s) => {
      const ids = new Set(selectedIdStr ? selectedIdStr.split(",") : []);
      if (s.mode === "strategy" || s.mode === "rebalancing") {
        if (ids.size !== 1) return INITIAL_STATE;
        if (
          s.mode === "rebalancing" &&
          s.analysis &&
          !ids.has(s.analysis.portfolio_id.toString())
        ) {
          return INITIAL_STATE;
        }
      }
      return s;
    });
  }, [selectedIdStr]);

  useEffect(() => {
    if (!autoAnalyzeId || !accountsReady) return;
    if (autoAnalyzedRef.current === autoAnalyzeId) return;
    const ids = new Set(selectedIdStr ? selectedIdStr.split(",") : []);
    if (!ids.has(autoAnalyzeId) || ids.size !== 1) return;
    autoAnalyzedRef.current = autoAnalyzeId;
    const cached = readCachedAnalysis(autoAnalyzeId, signatureRef.current);
    if (cached) {
      analyzedSignatureRef.current = cached.signature;
      setState({
        mode: "rebalancing",
        analysis: cached.analysis,
        analyzing: false,
        error: null,
        cashIsLive: cached.cashIsLive,
      });
      return;
    }
    void triggerRebalancingAnalysis(autoAnalyzeId);
    // selectedIds(Set)는 참조 비교가 불안정하므로 직렬화된 문자열로 의존성 추적
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAnalyzeId, selectedIdStr, accountsReady]);

  // 이미 분석 결과를 보여주고 있는 포트폴리오의 목표 비중이 저장으로 바뀌면 자동 재분석
  useEffect(() => {
    if (state.mode !== "rebalancing" || !state.analysis) return;
    if (!autoAnalyzeId || state.analysis.portfolio_id.toString() !== autoAnalyzeId) return;
    if (portfolioItemsSignature === undefined) return;
    if (analyzedSignatureRef.current === portfolioItemsSignature) return;
    void triggerRebalancingAnalysis(autoAnalyzeId);
  }, [
    portfolioItemsSignature,
    autoAnalyzeId,
    state.mode,
    state.analysis,
    triggerRebalancingAnalysis,
  ]);

  return { ...state, triggerRebalancingAnalysis, setMode };
}
