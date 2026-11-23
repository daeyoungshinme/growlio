import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import SegmentedControl from "@/components/common/SegmentedControl";
import ConfirmModal from "@/components/common/ConfirmModal";
import {
  DEFAULT_DIP_BUY_TIERS,
  deleteDipBuyPlan,
  upsertDipBuyPlan,
  type DipBuyIndex,
  type DipBuyPlan,
  type DipBuyPlanInput,
} from "@/api/dipBuy";
import { dipBuyPlanSchema } from "@/schemas/dipBuy";
import { FORM_LABEL, INPUT_SM, SELECT_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { invalidateDipBuyData } from "@/utils/queryInvalidation";
import { fmtKrw, fmtKrwPreview } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

interface Props {
  /** null = 새 설정 — `portfolioOptions`에서 포트폴리오를 고른다 */
  plan: DipBuyPlan | null;
  portfolioOptions: { id: string; name: string }[];
  defaultPortfolioId?: string | null;
  onClose: () => void;
}

const INDEX_OPTIONS: readonly { value: DipBuyIndex; label: string }[] = [
  { value: "QQQ", label: "나스닥100 (QQQ)" },
  { value: "SPY", label: "S&P500 (SPY)" },
];

const toNumber = (v: string) => (v.trim() === "" ? undefined : Number(v.replace(/,/g, "")));

interface TierDraft {
  drawdown: string;
  ratio: string;
}

const toDraft = (t: { drawdown_pct: number; ratio_pct: number }): TierDraft => ({
  drawdown: String(t.drawdown_pct),
  ratio: String(t.ratio_pct),
});

/** 낙폭 추매 안내 설정 — 기준 지수·여윳돈·구간(낙폭 %·여윳돈 비율 %), plans/147 */
export default function DipBuySettingsModal({
  plan,
  portfolioOptions,
  defaultPortfolioId,
  onClose,
}: Props) {
  const formId = useId();
  const reserveId = useId();
  const portfolioSelectId = useId();
  const tiersTitleId = useId();
  const qc = useQueryClient();
  const [portfolioId, setPortfolioId] = useState(
    plan?.portfolio_id ?? defaultPortfolioId ?? portfolioOptions[0]?.id ?? "",
  );
  const [indexTicker, setIndexTicker] = useState<DipBuyIndex>(plan?.index_ticker ?? "QQQ");
  const [reserve, setReserve] = useState(plan ? String(Math.round(plan.reserve_krw)) : "");
  const [tiers, setTiers] = useState<TierDraft[]>(
    (plan?.tiers ?? DEFAULT_DIP_BUY_TIERS).map(toDraft),
  );
  const [isActive, setIsActive] = useState(plan?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const done = (message: string) => {
    void invalidateDipBuyData(qc);
    toast(message, "success");
    onClose();
  };
  const saveMutation = useMutation({
    mutationFn: (data: DipBuyPlanInput) => upsertDipBuyPlan(portfolioId, data),
    onSuccess: () => done(plan ? "추매 안내 설정을 고쳤습니다" : "추매 안내를 켰습니다"),
    onError: (e) => setError(extractErrorMessage(e, "저장에 실패했습니다")),
  });
  const deleteMutation = useMutation({
    mutationFn: () => deleteDipBuyPlan(portfolioId),
    onSuccess: () => done("추매 안내를 지웠습니다"),
    onError: (e) => setError(extractErrorMessage(e, "삭제에 실패했습니다")),
  });

  const reserveValue = toNumber(reserve);
  const ratioTotal = tiers.reduce((sum, t) => sum + (toNumber(t.ratio) ?? 0), 0);

  const updateTier = (i: number, patch: Partial<TierDraft>) =>
    setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!portfolioId) {
      setError("포트폴리오를 골라주세요");
      return;
    }
    const parsed = dipBuyPlanSchema.safeParse({
      index_ticker: indexTicker,
      reserve_krw: reserveValue,
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
    saveMutation.mutate(parsed.data);
  };

  return (
    <Modal title={plan ? "추매 안내 설정" : "추매 안내 켜기"} onClose={onClose} size="sm">
      <ModalBody>
        <form id={formId} onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-gray-500 dark:text-gray-400 break-keep">
            매달 적립은 그대로 두고, 따로 정해 둔 여윳돈을 지수가 고점 대비 내려간 구간마다 나눠
            추매하도록 금액과 종목을 알려드려요. 주문은 자동으로 나가지 않아요.
          </p>
          {!plan && (
            <div>
              <label htmlFor={portfolioSelectId} className={FORM_LABEL}>
                포트폴리오
              </label>
              <select
                id={portfolioSelectId}
                value={portfolioId}
                onChange={(e) => setPortfolioId(e.target.value)}
                className={`${SELECT_SM} w-full`}
              >
                {portfolioOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                이 포트폴리오의 정기 적립식 자동매수와 같은 비율·계좌로 종목을 나눠요.
              </p>
            </div>
          )}
          <div>
            <p className={FORM_LABEL}>기준 지수 (52주 고점 대비 낙폭)</p>
            <SegmentedControl
              options={INDEX_OPTIONS}
              value={indexTicker}
              onChange={setIndexTicker}
              ariaLabel="기준 지수"
              stretch
            />
          </div>
          <div>
            <label htmlFor={reserveId} className={FORM_LABEL}>
              추매용 여윳돈 (원)
            </label>
            <input
              id={reserveId}
              value={reserve}
              onChange={(e) => setReserve(e.target.value)}
              inputMode="numeric"
              placeholder="10000000"
              className={`${INPUT_SM} w-full`}
            />
            {reserveValue != null && reserveValue > 0 && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                {fmtKrwPreview(reserveValue)}
              </p>
            )}
          </div>
          <div role="group" aria-labelledby={tiersTitleId} className="space-y-2">
            <p id={tiersTitleId} className={FORM_LABEL}>
              추매 구간 (낙폭이 이만큼 내려가면 여윳돈의 몇 %를 살지)
            </p>
            {tiers.map((t, i) => {
              const amount =
                reserveValue && toNumber(t.ratio)
                  ? (reserveValue * (toNumber(t.ratio) ?? 0)) / 100
                  : null;
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
                    aria-label={`${i + 1}구간 여윳돈 비율(%)`}
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
            알림 받기 (적립일 1~3일 전·당일 아침)
          </label>
          {error && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {error}
            </p>
          )}
          {plan && (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="text-xs text-red-600 dark:text-red-400 hover:underline"
            >
              추매 안내 지우기
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
          message="추매 안내 설정과 이번 하락의 추매 기록을 지울까요? 이미 산 종목은 그대로예요."
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
