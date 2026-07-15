import { useState } from "react";

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
    isDirty,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    startEditing,
  };
}
