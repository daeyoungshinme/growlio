import { useState } from "react";
import AmountUnitButtons from "@/components/common/AmountUnitButtons";
import { useAutoRebalancingDailyCap } from "@/hooks/useAutoRebalancingDailyCap";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { fmtKrw } from "@/utils/format";
import { SectionCard, inputClass, labelClass } from "./shared";

/** AUTO 리밸런싱 하루 합산 거래한도 — 유저 단위 안전장치. 비워 두면 무제한(기본값). */
export function AutoRebalancingDailyCapSection() {
  const { dailyCapKrw, maxOrderValueKrw, isLoading, save, isSaving } = useAutoRebalancingDailyCap();

  if (isLoading) return null;

  // 저장된 값이 바뀌면(저장·해제 직후 재조회) 입력칸을 새 값으로 다시 초기화한다.
  return (
    <DailyCapForm
      key={dailyCapKrw ?? "none"}
      dailyCapKrw={dailyCapKrw}
      maxOrderValueKrw={maxOrderValueKrw}
      onSave={save}
      isSaving={isSaving}
    />
  );
}

interface FormProps {
  dailyCapKrw: number | null;
  maxOrderValueKrw: number | null;
  onSave: (value: number | null) => void;
  isSaving: boolean;
}

function DailyCapForm({ dailyCapKrw, maxOrderValueKrw, onSave, isSaving }: FormProps) {
  const [draft, setDraft] = useState(dailyCapKrw != null ? String(Math.round(dailyCapKrw)) : "");
  const parsed = draft.trim() === "" ? null : Number(draft);
  const invalid = parsed != null && (!Number.isFinite(parsed) || parsed <= 0);
  const unchanged = parsed === (dailyCapKrw != null ? Math.round(dailyCapKrw) : null);

  return (
    <SectionCard title="AUTO 하루 거래한도">
      <div>
        <label htmlFor="auto-daily-cap" className={labelClass}>
          하루 합산 최대 거래대금 (원)
        </label>
        <input
          id="auto-daily-cap"
          type="number"
          inputMode="numeric"
          min={1}
          className={inputClass}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="비워두면 무제한"
          aria-invalid={invalid}
        />
        <AmountUnitButtons onAdd={(delta) => setDraft(String((parsed ?? 0) + delta))} />
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
          현재: {dailyCapKrw != null ? `하루 ${fmtKrw(dailyCapKrw)}` : "무제한"}
          {parsed != null && !invalid && !unchanged && ` → ${fmtKrw(parsed)}`}
          <br />
          자동(AUTO) 리밸런싱이 하루 동안 실행하는 주문 금액의 합계가 이 한도를 넘게 되면 실행을
          보류하고 알림을 보내드립니다.
          {maxOrderValueKrw != null &&
            ` 1건당 한도(${fmtKrw(maxOrderValueKrw)})와는 별도로 적용됩니다.`}
        </p>
        {invalid && (
          <p className="text-xs text-red-600 dark:text-red-400 mt-1">0보다 큰 금액을 입력하세요.</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onSave(parsed)}
          disabled={isSaving || invalid || unchanged}
          className={`bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors ${TOUCH_TARGET_MIN_MOBILE_ONLY}`}
        >
          {isSaving ? "저장 중..." : "저장"}
        </button>
        {dailyCapKrw != null && (
          <button
            type="button"
            onClick={() => onSave(null)}
            disabled={isSaving}
            className={`px-5 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors ${TOUCH_TARGET_MIN_MOBILE_ONLY}`}
          >
            한도 해제
          </button>
        )}
      </div>
    </SectionCard>
  );
}
