import { useCallback, useEffect, useRef, useState } from "react";
import { analyzePortfolio, type RebalancingAnalysis } from "@/api/rebalancing";
import { extractErrorMessage } from "@/utils/error";

type AnalysisMode = "rebalancing" | "strategy";

interface AnalysisState {
  mode: AnalysisMode | null;
  analysis: RebalancingAnalysis | null;
  analyzing: boolean;
  error: string | null;
}

const INITIAL_STATE: AnalysisState = { mode: null, analysis: null, analyzing: false, error: null };

export function useAnalysisState({
  autoAnalyzeId,
  selectedIdStr,
  portfolioItemsSignature,
}: {
  autoAnalyzeId?: string;
  selectedIdStr: string;
  /** 분석 대상 포트폴리오의 목표 비중(items) 직렬화 값 — 값이 바뀌면(저장으로 비중 변경) 자동 재분석 트리거 */
  portfolioItemsSignature?: string;
}) {
  const [state, setState] = useState<AnalysisState>(INITIAL_STATE);
  const autoAnalyzedRef = useRef<string | undefined>(undefined);

  // 마지막으로 분석을 요청한 시점의 비중 시그니처 — 이후 값이 달라지면 재분석이 필요하다는 신호
  const signatureRef = useRef(portfolioItemsSignature);
  signatureRef.current = portfolioItemsSignature;
  const analyzedSignatureRef = useRef<string | undefined>(undefined);

  const triggerRebalancingAnalysis = useCallback(
    async (id: string, depositKrwOverride?: number) => {
      analyzedSignatureRef.current = signatureRef.current;
      // 재분석 시 이전 결과(analysis)를 유지한 채 analyzing만 세워 화면이 비는 깜빡임을 방지
      setState((s) => ({
        mode: "rebalancing",
        analysis: s.mode === "rebalancing" ? s.analysis : null,
        analyzing: true,
        error: null,
      }));
      try {
        const result = await analyzePortfolio(id, undefined, depositKrwOverride);
        setState((s) => ({ ...s, analysis: result, analyzing: false }));
      } catch (err) {
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
    if (!autoAnalyzeId) return;
    if (autoAnalyzedRef.current === autoAnalyzeId) return;
    const ids = new Set(selectedIdStr ? selectedIdStr.split(",") : []);
    if (!ids.has(autoAnalyzeId) || ids.size !== 1) return;
    autoAnalyzedRef.current = autoAnalyzeId;
    void triggerRebalancingAnalysis(autoAnalyzeId);
    // selectedIds(Set)는 참조 비교가 불안정하므로 직렬화된 문자열로 의존성 추적
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAnalyzeId, selectedIdStr]);

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
