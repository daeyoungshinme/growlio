import { useCallback, useEffect, useRef, useState } from "react";

export const RECOMMENDATION_STEP = 6;

export type AutosaveStatus = "saving" | "saved" | "failed";

/** 6단계(추천 포트폴리오) 진입 시 1회 자동 저장하고, 그 저장 결과(`status`)와 재시도 함수를 돌려준다.
 *
 * 재진입(이전→다음) 시 값이 바뀌었을 수 있으므로 step이 6에서 벗어났다가 다시 들어올 때마다 다시
 * 트리거한다. onSave(=saveSettings)는 매 렌더 새 함수 참조라 effect deps에 직접 넣으면 무한
 * 재실행되므로 ref로 최신값만 참조한다. 완료 판정은 onSave가 돌려주는 성공 여부로 한다 —
 * 예전처럼 `saving` true→false 전환만 보면 저장이 실패해도 이전 설정 기준 추천을 보여줬다.
 * 늦게 끝난 이전 저장의 결과가 최신 상태를 덮어쓰지 않도록 실행 번호로 거른다. */
export function useRecommendationStepAutosave(step: number, onSave: () => Promise<boolean>) {
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);
  const enteredRecommendationStepRef = useRef(false);
  const runIdRef = useRef(0);
  const [status, setStatus] = useState<AutosaveStatus>("saving");

  const run = useCallback(() => {
    const runId = ++runIdRef.current;
    setStatus("saving");
    void onSaveRef.current().then((ok) => {
      if (runId === runIdRef.current) setStatus(ok ? "saved" : "failed");
    });
  }, []);

  useEffect(() => {
    if (step === RECOMMENDATION_STEP && !enteredRecommendationStepRef.current) {
      enteredRecommendationStepRef.current = true;
      run();
    } else if (step !== RECOMMENDATION_STEP) {
      enteredRecommendationStepRef.current = false;
    }
  }, [step, run]);

  return { status, retry: run };
}
