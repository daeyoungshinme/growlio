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
}: {
  autoAnalyzeId?: string;
  selectedIdStr: string;
}) {
  const [state, setState] = useState<AnalysisState>(INITIAL_STATE);
  const autoAnalyzedRef = useRef<string | undefined>(undefined);

  const triggerRebalancingAnalysis = useCallback(
    async (id: string, depositKrwOverride?: number) => {
      setState({ mode: "rebalancing", analysis: null, analyzing: true, error: null });
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

  return { ...state, triggerRebalancingAnalysis, setMode };
}
