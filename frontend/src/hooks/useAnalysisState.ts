import { useCallback, useEffect, useRef, useState } from "react";
import type { AssetAccount } from "@/api/assets";
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
 * 분석 진입 경로(버튼·포트폴리오 선택·딥링크·동기화 후 재분석)마다 예수금 기준이 달라 같은 포트폴리오의
 * 예수금·이탈이 경로별로 다르게 보이던 문제를 막기 위해 모든 분석이 이 값을 거친다(plans/63 P1-1).
 */
export async function fetchLiveDepositKrw(accounts: AssetAccount[]): Promise<number | undefined> {
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

  const triggerRebalancingAnalysis = useCallback(async (id: string) => {
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
      const depositKrwOverride = await fetchLiveDepositKrw(
        getDepositAccountsRef.current?.(id) ?? [],
      );
      if (seq !== requestSeqRef.current) return;
      const result = await analyzePortfolio(id, undefined, depositKrwOverride);
      if (seq !== requestSeqRef.current) return;
      setState((s) => ({
        ...s,
        analysis: result,
        analyzing: false,
        cashIsLive: depositKrwOverride !== undefined,
      }));
    } catch (err) {
      if (seq !== requestSeqRef.current) return;
      setState((s) => ({
        ...s,
        error: extractErrorMessage(err, "분석 중 오류가 발생했습니다."),
        analyzing: false,
      }));
    }
  }, []);

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
