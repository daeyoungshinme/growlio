import { useEffect, useRef, useState } from "react";

export const RECOMMENDATION_STEP = 6;

/** 6단계(추천 포트폴리오) 진입 시 1회 자동 저장하고, 그 저장이 끝났는지(`settingsPersisted`)를 돌려준다.
 *
 * 재진입(이전→다음) 시 값이 바뀌었을 수 있으므로 step이 6에서 벗어났다가 다시 들어올 때마다 다시
 * 트리거한다. onSave(=saveSettings)는 매 렌더 새 함수 참조라 effect deps에 직접 넣으면 무한
 * 재실행되므로 ref로 최신값만 참조한다. 저장 완료는 `saving`의 true→false 전환으로 감지한다. */
export function useRecommendationStepAutosave(step: number, saving: boolean, onSave: () => void) {
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);
  const enteredRecommendationStepRef = useRef(false);
  const [settingsPersisted, setSettingsPersisted] = useState(false);
  const prevSavingRef = useRef(saving);

  useEffect(() => {
    if (step === RECOMMENDATION_STEP && !enteredRecommendationStepRef.current) {
      enteredRecommendationStepRef.current = true;
      setSettingsPersisted(false);
      onSaveRef.current();
    } else if (step !== RECOMMENDATION_STEP) {
      enteredRecommendationStepRef.current = false;
    }
  }, [step]);

  useEffect(() => {
    if (prevSavingRef.current && !saving && enteredRecommendationStepRef.current) {
      setSettingsPersisted(true);
    }
    prevSavingRef.current = saving;
  }, [saving]);

  return settingsPersisted;
}
