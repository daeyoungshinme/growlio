import { useState } from "react";

/** 숫자 입력 필드를 부분 갱신 payload 값으로 바꾼다.
 * 값이 있으면 숫자, 사용자가 원래 있던 값을 지웠으면 null(백엔드가 비움),
 * 처음부터 비어 있었으면 undefined(키 생략 → 백엔드가 기존 값 유지).
 * 초기 폼이 설정 조회 실패 등으로 비어 있을 때 저장해도 기존 목표를 지우지 않기 위함이다. */
export function numberFieldPayload(
  value: string,
  initial: string | undefined,
): number | null | undefined {
  if (value) return Number(value);
  return initial ? null : undefined;
}

/** 편집 모달 폼의 공용 상태 머신 (editing/saving/dirty-check/close-confirm). */
export function useEditableSettingsForm<T>(emptyForm: T) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const [initialForm, setInitialForm] = useState<T | null>(null);
  const [form, setForm] = useState<T>(emptyForm);

  const isDirty =
    editing && initialForm !== null ? JSON.stringify(form) !== JSON.stringify(initialForm) : false;

  const handleCloseModal = () => {
    if (isDirty) {
      setShowCloseConfirm(true);
    } else {
      setEditing(false);
    }
  };

  const startEditing = (newForm: T) => {
    setForm(newForm);
    setInitialForm(newForm);
    setEditing(true);
  };

  return {
    editing,
    saving,
    setSaving,
    showCloseConfirm,
    form,
    setForm,
    initialForm,
    isDirty,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    startEditing,
  };
}
