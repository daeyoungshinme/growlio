import type { Dispatch, SetStateAction } from "react";
import FormInput from "@/components/common/FormInput";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import type { GoalForm } from "@/hooks/useGoalSettings";
import { fmtKrwPreview } from "@/utils/format";

/** 적립 계획 설정 편집(플랫 폼, 재설정용) — 최초 설정은 `GoalSettingWizard`. */
export default function GoalSettingsEditModal({
  form,
  setForm,
  saving,
  onSave,
  onClose,
}: {
  form: GoalForm;
  setForm: Dispatch<SetStateAction<GoalForm>>;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  return (
    <Modal title="적립 계획 설정 편집" onClose={onClose} size="md">
      <ModalBody padding="px-6 pb-6 pt-2" className="space-y-4">
        {[
          {
            label: "월 적립액 (원)",
            key: "monthly_deposit_amount",
            placeholder: "500000",
            inputMode: "numeric",
            isAmount: true,
          },
          {
            label: "목표 연수익률 (%)",
            key: "goal_annual_return_pct",
            placeholder: "8",
            inputMode: "decimal",
          },
          {
            label: "목표 금액 (원)",
            key: "goal_amount",
            placeholder: "500000000",
            inputMode: "numeric",
            isAmount: true,
          },
          {
            label: "투자 시작일",
            key: "goal_start_date",
            placeholder: "2024-01-01",
            type: "date",
          },
          {
            label: "투자 시작시점 자산 (원)",
            key: "goal_initial_amount",
            placeholder: "100000000",
            hint: "비워두면 스냅샷 자동 사용",
            inputMode: "numeric",
            isAmount: true,
          },
          {
            label: "연간 입금 목표 (원)",
            key: "annual_deposit_goal",
            placeholder: "24000000",
            inputMode: "numeric",
            isAmount: true,
          },
          {
            label: "은퇴 목표시점 (연도)",
            key: "retirement_target_year",
            placeholder: "2045",
            inputMode: "numeric",
          },
        ].map(({ label, key, placeholder, type, hint, inputMode, isAmount }) => {
          const value = form[key as keyof typeof form];
          return (
            <FormInput
              key={key}
              label={label}
              type={type ?? "number"}
              inputMode={type ? undefined : (inputMode as "numeric" | "decimal")}
              value={value}
              onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
              placeholder={placeholder}
              preview={isAmount && value ? fmtKrwPreview(Number(value)) : undefined}
              hint={hint}
            />
          );
        })}
      </ModalBody>
      <ModalFooter>
        <button
          onClick={onClose}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
        >
          취소
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {saving ? "저장 중..." : "저장"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
