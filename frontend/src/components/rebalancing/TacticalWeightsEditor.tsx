import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import type {
  RegimeWeightsTable,
  TacticalAsset,
  TacticalRegime,
  TacticalStrategyPayload,
} from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import { INPUT_SM, LABEL_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useCollapsible } from "@/hooks/useCollapsible";
import { DEFAULT_TILT_SHIFT_PCT, REGIME_LABEL, TACTICAL_ASSETS } from "./tacticalLabels";

const REGIME_ORDER: TacticalRegime[] = ["RISK_ON", "NEUTRAL", "RISK_OFF"];

const INPUT_LABEL: Record<TacticalAsset, string> = {
  QQQ: "QQQ",
  SPY: "SPY",
  DIA: "DIA",
  CASH: "현금",
};

const SHIFT_OPTIONS = [
  { value: "0", label: "끔" },
  { value: "5", label: "5%p" },
  { value: "10", label: "10%p" },
  { value: "15", label: "15%p" },
  { value: "20", label: "20%p" },
] as const;
type ShiftOption = (typeof SHIFT_OPTIONS)[number]["value"];

type Draft = Record<TacticalRegime, Record<TacticalAsset, string>>;

function toDraft(table: RegimeWeightsTable): Draft {
  const out = {} as Draft;
  for (const r of REGIME_ORDER) {
    // 응답에 없는 자산(구버전 저장값)은 0으로 — 백엔드 validate_regime_weights와 같은 규칙
    out[r] = Object.fromEntries(
      TACTICAL_ASSETS.map((a) => [a, String(table[r][a] ?? 0)]),
    ) as Record<TacticalAsset, string>;
  }
  return out;
}

function parseCell(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : null;
}

function rowSum(row: Record<TacticalAsset, string>): number | null {
  let sum = 0;
  for (const a of TACTICAL_ASSETS) {
    const n = parseCell(row[a]);
    if (n == null) return null;
    sum += n;
  }
  return sum;
}

function toShiftOption(v: number): ShiftOption {
  return (SHIFT_OPTIONS.find((o) => Number(o.value) === v)?.value ??
    String(DEFAULT_TILT_SHIFT_PCT)) as ShiftOption;
}

interface Props {
  regimeWeights: RegimeWeightsTable;
  isDefaultWeights: boolean;
  tiltShiftPct: number;
  notifyEnabled: boolean;
  saving: boolean;
  onSave: (payload: TacticalStrategyPayload) => void;
}

/**
 * 국면별 비중표 + 나스닥/S&P 틸트 이동폭 편집. 서버 값이 바뀌면 호출부가 `key`로 다시 마운트해 초안을 초기화한다
 * (effect로 props→state 동기화하지 않음).
 */
export default function TacticalWeightsEditor({
  regimeWeights,
  isDefaultWeights,
  tiltShiftPct,
  notifyEnabled,
  saving,
  onSave,
}: Props) {
  const [isOpen, toggle] = useCollapsible(false, "growlio:rebalancing:tactical-weights-open");
  const [draft, setDraft] = useState<Draft>(() => toDraft(regimeWeights));
  const [shift, setShift] = useState<ShiftOption>(() => toShiftOption(tiltShiftPct));

  const sums = REGIME_ORDER.map((r) => rowSum(draft[r]));
  const valid = sums.every((s) => s != null && Math.abs(s - 100) < 0.01);
  const dirty =
    REGIME_ORDER.some((r) =>
      TACTICAL_ASSETS.some((a) => parseCell(draft[r][a]) !== (regimeWeights[r][a] ?? 0)),
    ) || Number(shift) !== tiltShiftPct;
  const atDefaults = isDefaultWeights && tiltShiftPct === DEFAULT_TILT_SHIFT_PCT;

  const setCell = (r: TacticalRegime, a: TacticalAsset, v: string) =>
    setDraft((prev) => ({ ...prev, [r]: { ...prev[r], [a]: v } }));

  const save = () => {
    const table = {} as RegimeWeightsTable;
    for (const r of REGIME_ORDER) {
      table[r] = Object.fromEntries(TACTICAL_ASSETS.map((a) => [a, Number(draft[r][a])])) as Record<
        TacticalAsset,
        number
      >;
    }
    onSave({ notify_enabled: notifyEnabled, regime_weights: table, tilt_shift_pct: Number(shift) });
  };

  return (
    <CollapsibleCard
      icon={SlidersHorizontal}
      title="비중표 편집"
      isOpen={isOpen}
      onToggle={toggle}
      collapsedHint={
        isDefaultWeights ? "기본 비중표를 쓰는 중이에요" : "직접 정한 비중표를 쓰는 중이에요"
      }
    >
      <div className="flex flex-col gap-4">
        {REGIME_ORDER.map((r, idx) => {
          const sum = sums[idx];
          const ok = sum != null && Math.abs(sum - 100) < 0.01;
          return (
            <fieldset key={r} className="flex flex-col gap-1.5">
              <legend className="flex w-full items-center justify-between text-sm font-semibold">
                <span>{REGIME_LABEL[r]} 국면</span>
                <span
                  className={`text-xs font-normal ${ok ? "text-gray-500 dark:text-gray-400" : "text-red-600 dark:text-red-400"}`}
                >
                  합계 {sum == null ? "—" : `${sum}%`}
                  {!ok && " · 100%가 되어야 해요"}
                </span>
              </legend>
              <div className="grid grid-cols-4 gap-2">
                {TACTICAL_ASSETS.map((a) => (
                  <label key={a} className="flex flex-col gap-1">
                    <span className={LABEL_SM}>{INPUT_LABEL[a]} (%)</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      max={100}
                      step={5}
                      className={`${INPUT_SM} w-full`}
                      value={draft[r][a]}
                      onChange={(e) => setCell(r, a, e.target.value)}
                      aria-label={`${REGIME_LABEL[r]} 국면 ${INPUT_LABEL[a]} 비중`}
                    />
                  </label>
                ))}
              </div>
            </fieldset>
          );
        })}

        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold">나스닥·S&P 비중 조절폭</span>
          <SegmentedControl
            options={SHIFT_OPTIONS}
            value={shift}
            onChange={setShift}
            ariaLabel="나스닥·S&P 비중 조절폭"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            실질금리와 QQQ/SPY 상대강도를 보고 매달 한 번, 주식 몫 안에서 QQQ와 SPY 사이로 이만큼
            옮겨요. 현금 비중은 바뀌지 않아요.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            disabled={!valid || !dirty || saving}
            onClick={save}
          >
            비중표 저장
          </button>
          <button
            type="button"
            className={`${TOUCH_TARGET_MIN} px-4 rounded-lg text-sm text-gray-600 dark:text-gray-300 border border-gray-300 dark:border-gray-600 disabled:opacity-50`}
            disabled={atDefaults || saving}
            onClick={() =>
              onSave({
                notify_enabled: notifyEnabled,
                regime_weights: null,
                tilt_shift_pct: DEFAULT_TILT_SHIFT_PCT,
              })
            }
          >
            기본값으로
          </button>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500">
          저장하면 제안 비중과 아래 규칙 백테스트가 새 비중표로 다시 계산돼요. 포트폴리오 목표
          비중은 &lsquo;적용&rsquo;을 눌러야 바뀌어요.
        </p>
      </div>
    </CollapsibleCard>
  );
}
