import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { useCapsLockWarning } from "@/hooks/useCapsLockWarning";
import { INPUT_SM, LABEL_SM } from "@/constants/inputStyles";
import { toast } from "@/utils/toast";
import Modal from "@/components/common/Modal";

interface Props {
  onClose: () => void;
}

export default function ChangePasswordModal({ onClose }: Props) {
  const changePassword = useAuthStore((s) => s.changePassword);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const { isCapsLockOn: isCurrentCapsLockOn, handleKeyEvent: handleCurrentKeyEvent } =
    useCapsLockWarning();
  const { isCapsLockOn: isNewCapsLockOn, handleKeyEvent: handleNewKeyEvent } = useCapsLockWarning();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 8) {
      setError("새 비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("새 비밀번호가 일치하지 않습니다.");
      return;
    }

    setSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      toast("비밀번호가 변경되었습니다", "success");
      onClose();
    } catch (err: unknown) {
      const msg = (err as Error)?.message ?? "";
      if (
        msg.toLowerCase().includes("should not be too common") ||
        msg.toLowerCase().includes("data breach")
      ) {
        setError("유출된 비밀번호입니다. 다른 비밀번호를 사용해주세요.");
      } else if (msg) {
        setError(msg);
      } else {
        setError("비밀번호 변경에 실패했습니다. 다시 시도해주세요.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal onClose={onClose} title="비밀번호 변경" size="sm">
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        <div>
          <label htmlFor="change-password-current" className={`block ${LABEL_SM} mb-1`}>
            현재 비밀번호
          </label>
          <input
            id="change-password-current"
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            onKeyDown={handleCurrentKeyEvent}
            onKeyUp={handleCurrentKeyEvent}
            required
            className={`w-full ${INPUT_SM}`}
          />
          {isCurrentCapsLockOn && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              Caps Lock이 켜져 있습니다
            </p>
          )}
        </div>
        <div>
          <label htmlFor="change-password-new" className={`block ${LABEL_SM} mb-1`}>
            새 비밀번호
          </label>
          <input
            id="change-password-new"
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            onKeyDown={handleNewKeyEvent}
            onKeyUp={handleNewKeyEvent}
            required
            placeholder="8자 이상"
            className={`w-full ${INPUT_SM}`}
          />
          {isNewCapsLockOn && (
            <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
              Caps Lock이 켜져 있습니다
            </p>
          )}
        </div>
        <div>
          <label htmlFor="change-password-confirm" className={`block ${LABEL_SM} mb-1`}>
            새 비밀번호 확인
          </label>
          <input
            id="change-password-confirm"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className={`w-full ${INPUT_SM}`}
          />
        </div>

        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

        <div className="flex justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={
              saving ||
              currentPassword.length === 0 ||
              newPassword.length === 0 ||
              confirmPassword.length === 0
            }
            className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg transition-colors"
          >
            {saving && <Loader2 size={14} className="animate-spin" />}
            변경하기
          </button>
        </div>
      </form>
    </Modal>
  );
}
