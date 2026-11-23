import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import SegmentedControl from "@/components/common/SegmentedControl";
import ConfirmModal from "@/components/common/ConfirmModal";
import {
  createDipBuyRule,
  DEFAULT_DIP_BUY_TIERS,
  deleteDipBuyRule,
  DIP_BUY_INDEX_LABEL,
  updateDipBuyRule,
  type DipBuyIndex,
  type DipBuyRule,
  type DipBuyRuleInput,
} from "@/api/dipBuy";
import { dipBuyRuleSchema } from "@/schemas/dipBuy";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { invalidateDipBuyData } from "@/utils/queryInvalidation";
import { fmtKrw } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

interface Props {
  /** null = 새 규칙 — `availableIndexes`에서 지수를 고른다 */
  rule: DipBuyRule | null;
  /** 새 규칙에서 고를 수 있는 지수(아직 규칙이 없는 지수) */
  availableIndexes: readonly DipBuyIndex[];
  /** 다른 규칙들이 이미 가져간 배분 합계(%) */
  otherAllocationPct: number;
  /** 배분 % → 금액 미리보기용 여윳돈 풀(남은 여윳돈 + 진행 중 사이클 추매액) */
  poolKrw: number;
  onClose: () => void;
}

const toNumber = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));

interface TierDraft {
  drawdown: string;
  ratio: string;
}

const toDraft = (t: { drawdown_pct: number; ratio_pct: number }): TierDraft => ({
  drawdown: String(t.drawdown_pct),
  ratio: String(t.ratio_pct),
});

/** 지수별 추매 규칙 — 기준 지수·여윳돈 배분 %·구간(낙폭 %·몫 비율 %), plans/148 */
export default function DipBuyRuleModal({
  rule,
  availableIndexes,
  otherAllocationPct,
  poolKrw,
  onClose,
}: Props) {
  const formId = useId();
  const allocationId = useId();
  const tiersTitleId = useId();
  const qc = useQueryClient();
  const indexChoices = rule
    ? Array.from(new Set<DipBuyIndex>([rule.index_ticker, ...availableIndexes]))
    : [...availableIndexes];
  const [indexTicker, setIndexTicker] = useState<DipBuyIndex>(
    rule?.index_ticker ?? indexChoices[0] ?? "QQQ",
  );
  const leftPct = Math.max(0, 100 - otherAllocationPct);
  const [allocation, setAllocation] = useState(String(rule?.allocation_pct ?? leftPct));
  const [tiers, setTiers] = useState<TierDraft[]>(
    (rule?.tiers ?? DEFAULT_DIP_BUY_TIERS).map(toDraft),
  );
  const [isActive, setIsActive] = useState(rule?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const done = (message: string) => {
    void invalidateDipBuyData(qc);
    toast(message, "success");
    onClose();
  };
  const saveMutation = useMutation({
    mutationFn: (data: DipBuyRuleInput) =>
      rule ? updateDipBuyRule(rule.id, data) : createDipBuyRule(data),
    onSuccess: () => done(rule ? "추매 규칙을 고쳤습니다" : "추매 규칙을 추가했습니다"),
    onError: (e) => setError(extractErrorMessage(e, "저장에 실패했습니다")),
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteDipBuyRule(rule?.id ?? ""),
    onSuccess: () => done("추매 규칙을 지웠습니다"),
    onError: (e) => setError(extractErrorMessage(e, "삭제에 실패했습니다")),
  });

  const allocationValue = toNumber(allocation);
  const shareKrw = allocationValue ? (poolKrw * allocationValue) / 100 : 0;
  const ratioTotal = tiers.reduce((sum, t) => sum + (toNumber(t.ratio) ?? 0), 0);

  const updateTier = (i: number, patch: Partial<TierDraft>) =>
    setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const parsed = dipBuyRuleSchema.safeParse({
      index_ticker: indexTicker,
      allocation_pct: allocationValue,
      tiers: tiers.map((t) => ({
        drawdown_pct: toNumber(t.drawdown),
        ratio_pct: toNumber(t.ratio),
      })),
      is_active: isActive,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "입력값을 확인해주세요");
      return;
    }
    if (parsed.data.allocation_pct > leftPct) {
      setError(`다른 규칙이 ${otherAllocationPct}%를 쓰고 있어 ${leftPct}%까지 정할 수 있어요`);
      return;
    }
    saveMutation.mutate(parsed.data);
  };

  return (
    <Modal title={rule ? "추매 규칙 설정" : "추매 규칙 추가"} onClose={onClose} size="sm">
      <ModalBody>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <div>
            <p className={FORM_LABEL}>기준 지수 (52주 고점 대비 낙폭)</p>
            {indexChoices.length > 1 ? (
              <SegmentedControl
                options={indexChoices.map((v) => ({ value: v, label: DIP_BUY_INDEX_LABEL[v] }))}
                value={indexTicker}
                onChange={setIndexTicker}
                ariaLabel="기준 지수"
                stretch
              />
            ) : (
              <p className="text-sm text-gray-800 dark:text-gray-200">
                {DIP_BUY_INDEX_LABEL[indexTicker]}
              </p>
            )}
          </div>
          <div>
            <label htmlFor={allocationId} className={FORM_LABEL}>
              여윳돈 배분 (%)
            </label>
            <input
              id={allocationId}
              value={allocation}
              onChange={(e) => setAllocation(e.target.value)}
              inputMode="decimal"
              className={`${INPUT_SM} w-full`}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400 break-keep">
              {otherAllocationPct > 0
                ? `다른 규칙이 ${otherAllocationPct}%를 써서 ${leftPct}%까지 정할 수 있어요. `
                : ""}
              {shareKrw > 0 ? `이 규칙 몫 약 ${fmtKrw(shareKrw)}` : ""}
            </p>
          </div>
          <div role="group" aria-labelledby={tiersTitleId} className="space-y-2">
            <p id={tiersTitleId} className={FORM_LABEL}>
              추매 구간 (낙폭이 이만큼 내려가면 이 규칙 몫의 몇 %를 살지)
            </p>
            {tiers.map((t, i) => {
              const amount =
                shareKrw && toNumber(t.ratio) ? (shareKrw * (toNumber(t.ratio) ?? 0)) / 100 : null;
              return (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <span className="text-gray-500 dark:text-gray-400 shrink-0">−</span>
                  <input
                    aria-label={`${i + 1}구간 낙폭(%)`}
                    value={t.drawdown}
                    onChange={(e) => updateTier(i, { drawdown: e.target.value })}
                    inputMode="decimal"
                    className={`${INPUT_SM} w-16`}
                  />
                  <span className="text-gray-500 dark:text-gray-400 shrink-0">% →</span>
                  <input
                    aria-label={`${i + 1}구간 비율(%)`}
                    value={t.ratio}
                    onChange={(e) => updateTier(i, { ratio: e.target.value })}
                    inputMode="decimal"
                    className={`${INPUT_SM} w-16`}
                  />
                  <span className="text-gray-500 dark:text-gray-400 shrink-0">%</span>
                  <span className="flex-1 text-right text-xs text-gray-500 dark:text-gray-400">
                    {amount != null ? fmtKrw(amount) : ""}
                  </span>
                  {tiers.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setTiers((prev) => prev.filter((_, idx) => idx !== i))}
                      className={`${TOUCH_TARGET_MIN} text-xs text-gray-400 hover:text-red-600`}
                      aria-label={`${i + 1}구간 삭제`}
                    >
                      삭제
                    </button>
                  )}
                </div>
              );
            })}
            <div className="flex items-center justify-between text-xs">
              <span
                className={
                  ratioTotal > 100
                    ? "text-red-600 dark:text-red-400"
                    : "text-gray-500 dark:text-gray-400"
                }
              >
                비율 합계 {ratioTotal}% (100% 이하)
              </span>
              {tiers.length < 3 && (
                <button
                  type="button"
                  onClick={() => setTiers((prev) => [...prev, { drawdown: "", ratio: "" }])}
                  className={`${TOUCH_TARGET_MIN} text-blue-600 dark:text-blue-400 hover:underline`}
                >
                  구간 추가
                </button>
              )}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            이 규칙 사용
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
          {rule && (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="text-xs text-red-600 dark:text-red-400 hover:underline"
            >
              이 규칙 지우기
            </button>
          )}
        </form>
      </ModalBody>
      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          className={`${TOUCH_TARGET_MIN} flex-1 px-5 py-2 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300`}
        >
          취소
        </button>
        <button
          type="submit"
          form={formId}
          disabled={saveMutation.isPending}
          className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {saveMutation.isPending ? "저장 중..." : "저장"}
        </button>
      </ModalFooter>
      {confirmDelete && (
        <ConfirmModal
          message="이 추매 규칙과 이번 하락의 추매 기록을 지울까요? 이미 산 종목과 여윳돈은 그대로예요."
          confirmLabel="지우기"
          onConfirm={() => {
            setConfirmDelete(false);
            deleteMutation.mutate();
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </Modal>
  );
}
