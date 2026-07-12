import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteAccount } from "@/api/auth";
import { supabase } from "@/lib/supabase";
import { AUTH_ME_CACHE_KEY, useAuthStore } from "@/stores/authStore";
import { PERSIST_CACHE_KEY } from "@/constants/queryConfig";
import { INPUT_SM, LABEL_SM } from "@/constants/inputStyles";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import Modal from "@/components/common/Modal";

interface Props {
  onClose: () => void;
}

export default function DeleteAccountModal({ onClose }: Props) {
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");

  const deleteMutation = useMutation({
    mutationFn: () => deleteAccount(password),
    onSuccess: async () => {
      queryClient.clear();
      window.localStorage.removeItem(PERSIST_CACHE_KEY);
      window.localStorage.removeItem(AUTH_ME_CACHE_KEY);
      await supabase.auth.signOut().catch(() => {});
      useAuthStore.setState({
        isAuthenticated: false,
        userId: null,
        email: null,
        needsPasswordReset: false,
      });
      toast("회원 탈퇴가 완료되었습니다", "success");
      onClose();
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return (
    <Modal onClose={onClose} title="회원 탈퇴" size="sm">
      <div className="p-4 space-y-4">
        <div className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200">
          <AlertTriangle size={18} className="text-red-500 mt-0.5 shrink-0" aria-hidden="true" />
          <p>
            탈퇴 시 계좌·거래내역·포트폴리오·리밸런싱 이력 등 저장된 모든 데이터가 영구적으로
            삭제되며 되돌릴 수 없습니다.
          </p>
        </div>

        <div>
          <label htmlFor="delete-account-password" className={`block ${LABEL_SM} mb-1`}>
            비밀번호 확인
          </label>
          <input
            id="delete-account-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`w-full ${INPUT_SM}`}
            placeholder="비밀번호를 입력하세요"
          />
        </div>

        <div className="flex justify-end gap-3 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            취소
          </button>
          <button
            type="button"
            disabled={password.length === 0 || deleteMutation.isPending}
            onClick={() => deleteMutation.mutate()}
            className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 rounded-lg transition-colors"
          >
            {deleteMutation.isPending && <Loader2 size={14} className="animate-spin" />}
            탈퇴하기
          </button>
        </div>
      </div>
    </Modal>
  );
}
