import { useId, type Dispatch, type FormEvent, type SetStateAction } from "react";
import FormInput from "@/components/common/FormInput";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import type { DividendPlanForm } from "@/hooks/useDividendPlanSettings";
import { fmtKrwPreview } from "@/utils/format";

/** 배당 계획 설정(연간 배당 목표) 편집 — 키보드 Enter로도 저장되게 `<form id>` + 버튼 `form=` */
export default function DividendSettingsModal({
  form,
  setForm,
  saving,
  onSave,
  onClose,
}: {
  form: DividendPlanForm;
  setForm: Dispatch<SetStateAction<DividendPlanForm>>;
  saving: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const formId = useId();
  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!saving) onSave();
  };
  return (
    <Modal title="배당 계획 설정" onClose={onClose} size="md">
      <ModalBody padding="px-6 pb-6 pt-2" className="space-y-4">
        <form id={formId} onSubmit={handleSubmit}>
          <FormInput
            label="목표 연간 배당금 (원)"
            type="number"
            inputMode="numeric"
            value={form.annual_dividend_goal}
            onChange={(e) => setForm((f) => ({ ...f, annual_dividend_goal: e.target.value }))}
            placeholder="10000000"
            preview={
              form.annual_dividend_goal
                ? fmtKrwPreview(Number(form.annual_dividend_goal))
                : undefined
            }
            hint="예상 연배당이 이 금액을 넘으면 목표 달성"
          />
        </form>
      </ModalBody>
      <ModalFooter>
        <button
          type="button"
          onClick={onClose}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
        >
          취소
        </button>
        <button
          type="submit"
          form={formId}
          disabled={saving}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {saving ? "저장 중..." : "저장"}
        </button>
      </ModalFooter>
    </Modal>
  );
}
