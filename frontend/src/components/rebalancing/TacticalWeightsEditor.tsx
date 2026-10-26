import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import type {
  RegimeWeightsTable,
  TacticalAsset,
  TacticalRegime,
  TacticalStrategyPayload,
} from "@/api/tactical";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import SegmentedControl from "@/components/portfolio/allocation/SegmentedControl";
import { INPUT_SM, LABEL_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useCollapsible } from "@/hooks/useCollapsible";
import {
  DEFAULT_DIP_SHIFT_PCT,
  DEFAULT_TILT_SHIFT_PCT,
  LEVERAGED_ASSETS,
  REGIME_LABEL,
  TACTICAL_ASSETS,
  TACTICAL_PRESETS,
  type TacticalPreset,
} from "./tacticalLabels";

const REGIME_ORDER: TacticalRegime[] = ["RISK_ON", "NEUTRAL", "RISK_OFF"];

const INPUT_LABEL: Record<TacticalAsset, string> = {
  QQQ: "나스닥100",
  SPY: "S&P500",
  DIA: "다우",
  QLD: "나스닥 2배",
  SSO: "S&P 2배",
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

/** 웅덩이 투입 최대폭 — 백엔드 tactical_dip.MAX_DIP_SHIFT_PCT(30) 이내 */
const DIP_OPTIONS = [
  { value: "0", label: "끔" },
  { value: "10", label: "10%p" },
  { value: "20", label: "20%p" },
  { value: "30", label: "30%p" },
] as const;
type DipOption = (typeof DIP_OPTIONS)[number]["value"];

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

function presetMatches(
  preset: TacticalPreset,
  draft: Draft,
  shift: ShiftOption,
  dip: DipOption,
  useMacro: boolean,
): boolean {
  return (
    REGIME_ORDER.every((r) =>
      TACTICAL_ASSETS.every((a) => parseCell(draft[r][a]) === preset.weights[r][a]),
    ) &&
    Number(shift) === preset.tiltShiftPct &&
    Number(dip) === preset.dipShiftPct &&
    useMacro === preset.useMacro
  );
}

function toShiftOption(v: number): ShiftOption {
  return (SHIFT_OPTIONS.find((o) => Number(o.value) === v)?.value ??
    String(DEFAULT_TILT_SHIFT_PCT)) as ShiftOption;
}

function toDipOption(v: number): DipOption {
  return (DIP_OPTIONS.find((o) => Number(o.value) === v)?.value ??
    String(DEFAULT_DIP_SHIFT_PCT)) as DipOption;
}

interface Props {
  regimeWeights: RegimeWeightsTable;
  isDefaultWeights: boolean;
  tiltShiftPct: number;
  dipShiftPct: number;
  useMacro: boolean;
  notifyEnabled: boolean;
  saving: boolean;
  onSave: (payload: TacticalStrategyPayload) => void;
}

/**
 * 프리셋(안정·균형·성장·레버리지) + 국면별 비중표 + 나스닥/S&P 틸트 이동폭 + 웅덩이 투입폭 + 매크로 반영 편집. 서버 값이 바뀌면 호출부가 `key`로 다시 마운트해 초안을 초기화한다
 * (effect로 props→state 동기화하지 않음).
 */
export default function TacticalWeightsEditor({
  regimeWeights,
  isDefaultWeights,
  tiltShiftPct,
  dipShiftPct,
  useMacro,
  notifyEnabled,
  saving,
  onSave,
}: Props) {
  const [isOpen, toggle] = useCollapsible(false, "growlio:rebalancing:tactical-weights-open");
  const [draft, setDraft] = useState<Draft>(() => toDraft(regimeWeights));
  const [shift, setShift] = useState<ShiftOption>(() => toShiftOption(tiltShiftPct));
  const [dip, setDip] = useState<DipOption>(() => toDipOption(dipShiftPct));
  const [macro, setMacro] = useState(useMacro);

  const sums = REGIME_ORDER.map((r) => rowSum(draft[r]));
  const valid = sums.every((s) => s != null && Math.abs(s - 100) < 0.01);
  const dirty =
    REGIME_ORDER.some((r) =>
      TACTICAL_ASSETS.some((a) => parseCell(draft[r][a]) !== (regimeWeights[r][a] ?? 0)),
    ) ||
    Number(shift) !== tiltShiftPct ||
    Number(dip) !== dipShiftPct ||
    macro !== useMacro;
  const atDefaults =
    isDefaultWeights &&
    tiltShiftPct === DEFAULT_TILT_SHIFT_PCT &&
    dipShiftPct === DEFAULT_DIP_SHIFT_PCT &&
    useMacro;
  const activePreset = TACTICAL_PRESETS.find((p) => presetMatches(p, draft, shift, dip, macro));

  const applyPreset = (p: TacticalPreset) => {
    setDraft(toDraft(p.weights));
    setShift(toShiftOption(p.tiltShiftPct));
    setDip(toDipOption(p.dipShiftPct));
    setMacro(p.useMacro);
  };
  // 레버리지 비중이 있는 국면 — 방어 국면 보유는 특히 경고
  const leveragedIn = REGIME_ORDER.filter((r) =>
    [...LEVERAGED_ASSETS].some((a) => (parseCell(draft[r][a]) ?? 0) > 0),
  );

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
    onSave({
      notify_enabled: notifyEnabled,
      regime_weights: table,
      tilt_shift_pct: Number(shift),
      dip_shift_pct: Number(dip),
      use_macro: macro,
    });
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
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold">프리셋</span>
          <div className="grid grid-cols-2 gap-2">
            {TACTICAL_PRESETS.map((p) => {
              const active = activePreset?.key === p.key;
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={active}
                  className={`${TOUCH_TARGET_MIN} flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors ${
                    active
                      ? "border-blue-500 bg-blue-50 dark:border-blue-400 dark:bg-blue-900/20"
                      : "border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500"
                  }`}
                  onClick={() => applyPreset(p)}
                >
                  <span className="text-sm font-semibold">{p.label}</span>
                  <span className="text-xs text-gray-500 dark:text-gray-400">{p.description}</span>
                  <span className="text-xs text-gray-600 dark:text-gray-300">
                    연 {p.backtest.cagrPct}% · 최대낙폭 {p.backtest.mddPct}%
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            2006~2026년 20년 백테스트(현금 국채 이자·거래비용 반영). 나스닥 강세기 기준이라 미래를
            보장하지 않아요. 누르면 아래 값이 채워지고, 저장해야 반영돼요.
          </p>
        </div>

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
              <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
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

        {leveragedIn.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            QLD·SSO는 하루 수익률의 2배를 따라가는 레버리지 ETF라 횡보·급락 구간에서 손실이 2배보다
            커질 수 있어요(복리 감쇠).
            {leveragedIn.includes("RISK_OFF") &&
              " 방어 국면에 레버리지를 두면 하락장 방어 효과가 크게 줄어요."}
          </p>
        )}

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

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-semibold">매크로 신호 반영</span>
            <ToggleSwitch checked={macro} onChange={setMacro} ariaLabel="매크로 신호 반영" />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            끄면 SPY·QQQ 200일선 추세만으로 국면을 판단해요. 과거 백테스트에선 수익률이 더 높았지만
            최근 10년 최대낙폭은 커졌어요.
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold">웅덩이 매수 투입폭</span>
          <SegmentedControl
            options={DIP_OPTIONS}
            value={dip}
            onChange={setDip}
            ariaLabel="웅덩이 매수 투입폭"
          />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            공격 국면에서 QQQ가 60일선·120일선까지 눌리거나 120일선 아래에서 RSI가 35 미만이면,
            단계마다 이 폭의 1/3씩 현금을 주식으로 옮겨요(현금 비중이 한도). 모든 이평선 위로
            회복하거나 공격 국면이 끝나면 다시 현금으로 돌려요. 과거 백테스트 효과는 연 0.3%p
            안팎으로 작아요.
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
                dip_shift_pct: DEFAULT_DIP_SHIFT_PCT,
                use_macro: true,
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
