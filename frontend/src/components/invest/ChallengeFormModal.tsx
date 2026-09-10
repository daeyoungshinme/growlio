import { useMemo, useState } from "react";
import type { Challenge, ChallengeCreatePayload, ChallengeType } from "@/api/challenges";
import type { AssetAccount } from "@/api/assets";
import type { SettingsData } from "@/api/settings";
import Modal from "@/components/common/Modal";
import ConfirmModal from "@/components/common/ConfirmModal";
import FormInput from "@/components/common/FormInput";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import { challengeFormSchema } from "@/schemas/challenge";
import { isStockAccount } from "@/utils/accounts";
import { fmtKrwPreview } from "@/utils/format";
import { toast } from "@/utils/toast";
import { INPUT_SM, LABEL_SM } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

const TYPE_OPTIONS: { value: ChallengeType; label: string }[] = [
  { value: "DEPOSIT", label: "매달 적립" },
  { value: "RETURN_PCT", label: "수익률" },
  { value: "TARGET_VALUE", label: "평가금액" },
];

interface FormState {
  title: string;
  challenge_type: ChallengeType;
  target_amount: string;
  target_pct: string;
  target_months: string;
  account_id: string;
  start_month: string;
  deadline_month: string;
  reminder_enabled: boolean;
}

function currentMonth(): string {
  return new Date().toISOString().slice(0, 7);
}

interface Props {
  challenge?: Challenge;
  accounts: AssetAccount[];
  settings?: SettingsData;
  submitting: boolean;
  onClose: () => void;
  onSubmit: (payload: ChallengeCreatePayload) => void;
}

export default function ChallengeFormModal({
  challenge,
  accounts,
  settings,
  submitting,
  onClose,
  onSubmit,
}: Props) {
  const isEdit = !!challenge;
  const [form, setForm] = useState<FormState>(() => ({
    title: challenge?.title ?? "",
    challenge_type: challenge?.challenge_type ?? "DEPOSIT",
    target_amount: challenge?.target_amount != null ? String(challenge.target_amount) : "",
    target_pct: challenge?.target_pct != null ? String(challenge.target_pct) : "",
    target_months: challenge?.target_months != null ? String(challenge.target_months) : "",
    account_id: challenge?.account_id ?? "",
    start_month: challenge?.start_month ?? currentMonth(),
    deadline_month: challenge?.deadline_month ?? "",
    reminder_enabled: challenge?.reminder_enabled ?? true,
  }));
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const stockAccounts = useMemo(
    () => accounts.filter((a) => isStockAccount(a.asset_type) && a.is_active),
    [accounts],
  );

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDirty(true);
  };

  const isDeposit = form.challenge_type === "DEPOSIT";

  const prefillFromGoal = () => {
    if (!settings) return;
    if (isDeposit && settings.monthly_deposit_amount) {
      set("target_amount", String(settings.monthly_deposit_amount));
    } else if (form.challenge_type === "RETURN_PCT" && settings.goal_annual_return_pct) {
      set("target_pct", String(settings.goal_annual_return_pct));
    } else if (form.challenge_type === "TARGET_VALUE" && settings.goal_amount) {
      set("target_amount", String(settings.goal_amount));
    } else {
      toast("적립 계획에 가져올 값이 없어요", "error");
    }
  };

  const handleSubmit = () => {
    const parsed = challengeFormSchema.safeParse({
      title: form.title,
      challenge_type: form.challenge_type,
      target_amount: form.target_amount ? Number(form.target_amount) : null,
      target_pct: form.target_pct ? Number(form.target_pct) : null,
      target_months: form.target_months ? Number(form.target_months) : null,
      account_id: isDeposit && form.account_id ? form.account_id : null,
      start_month: form.start_month,
      deadline_month: form.deadline_month || null,
      reminder_enabled: form.reminder_enabled,
    });
    if (!parsed.success) {
      const next: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const path = String(issue.path[0] ?? "form");
        if (!next[path]) next[path] = issue.message;
      }
      setErrors(next);
      return;
    }
    setErrors({});
    onSubmit(parsed.data as ChallengeCreatePayload);
  };

  const requestClose = () => (dirty ? setConfirmClose(true) : onClose());

  return (
    <>
      <Modal title={isEdit ? "챌린지 편집" : "새 챌린지"} onClose={requestClose} size="md">
        <div className="overflow-y-auto overscroll-contain px-6 pb-6 pt-2 space-y-4 flex-1">
          {!isEdit && (
            <div>
              <span className={`block mb-1 ${LABEL_SM}`}>유형</span>
              <div className="grid grid-cols-3 gap-2">
                {TYPE_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => set("challenge_type", o.value)}
                    className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 py-2 text-sm rounded-lg border transition-colors ${
                      form.challenge_type === o.value
                        ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300"
                        : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300"
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <FormInput
            label="제목"
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            placeholder="예: 2026 매달 50만원 적립"
            required
            error={errors.title}
          />

          {settings && (
            <button
              type="button"
              onClick={prefillFromGoal}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
            >
              적립 계획 목표에서 가져오기
            </button>
          )}

          {isDeposit && (
            <>
              <FormInput
                label="월 목표액 (원, 선택)"
                type="number"
                inputMode="numeric"
                value={form.target_amount}
                onChange={(e) => set("target_amount", e.target.value)}
                placeholder="500000"
                hint="비워두면 매달 입금만 해도 달성으로 인정돼요"
                preview={form.target_amount ? fmtKrwPreview(Number(form.target_amount)) : undefined}
                error={errors.target_amount}
              />
              <FormInput
                label="연속 목표 개월수 (선택)"
                type="number"
                inputMode="numeric"
                value={form.target_months}
                onChange={(e) => set("target_months", e.target.value)}
                placeholder="12"
                hint="설정하면 진행률이 표시돼요"
                error={errors.target_months}
              />
              {stockAccounts.length > 0 && (
                <div>
                  <label htmlFor="challenge-account" className={`block mb-1 ${LABEL_SM}`}>
                    대상 계좌
                  </label>
                  <select
                    id="challenge-account"
                    className={`w-full ${INPUT_SM}`}
                    value={form.account_id}
                    onChange={(e) => set("account_id", e.target.value)}
                  >
                    <option value="">전체 투자자산</option>
                    {stockAccounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {form.challenge_type === "RETURN_PCT" && (
            <FormInput
              label="목표 수익률 (%)"
              type="number"
              inputMode="decimal"
              value={form.target_pct}
              onChange={(e) => set("target_pct", e.target.value)}
              placeholder="10"
              required
              error={errors.target_pct}
            />
          )}

          {form.challenge_type === "TARGET_VALUE" && (
            <FormInput
              label="목표 평가금액 (원)"
              type="number"
              inputMode="numeric"
              value={form.target_amount}
              onChange={(e) => set("target_amount", e.target.value)}
              placeholder="100000000"
              required
              preview={form.target_amount ? fmtKrwPreview(Number(form.target_amount)) : undefined}
              error={errors.target_amount}
            />
          )}

          {!isEdit && (
            <FormInput
              label="시작 월"
              type="month"
              value={form.start_month}
              onChange={(e) => set("start_month", e.target.value)}
              error={errors.start_month}
            />
          )}

          <FormInput
            label="마감 월 (선택)"
            type="month"
            value={form.deadline_month}
            onChange={(e) => set("deadline_month", e.target.value)}
            error={errors.deadline_month}
          />

          <div className="flex items-center justify-between">
            <span className={LABEL_SM}>독려·결산 알림 받기</span>
            <ToggleSwitch
              checked={form.reminder_enabled}
              onChange={(v) => set("reminder_enabled", v)}
              ariaLabel="이 챌린지 알림"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={requestClose}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
            >
              취소
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            >
              {submitting ? "저장 중..." : isEdit ? "저장" : "만들기"}
            </button>
          </div>
        </div>
      </Modal>

      {confirmClose && (
        <ConfirmModal
          message="저장하지 않은 변경사항이 있습니다. 닫으시겠습니까?"
          confirmLabel="닫기"
          cancelLabel="계속 편집"
          danger={false}
          onConfirm={() => {
            setConfirmClose(false);
            onClose();
          }}
          onCancel={() => setConfirmClose(false)}
        />
      )}
    </>
  );
}
