import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteAccountCredentials, type CredentialBroker } from "@/api/assets";
import ConfirmModal from "@/components/common/ConfirmModal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { invalidateBrokerCredentialData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

const BROKER_LABELS: Record<CredentialBroker, string> = {
  kis: "KIS",
  kiwoom: "키움",
  toss: "토스",
};

const CONSEQUENCE: Record<CredentialBroker, string> = {
  kis: "설정에 등록한 공통 KIS 키가 있으면 그 키로 계속 동기화되고, 없으면 자동 동기화·자동 매매가 중단됩니다.",
  kiwoom: "새 키를 입력하기 전까지 이 계좌의 자동 동기화·자동 매매가 중단됩니다.",
  toss: "새 키를 입력하기 전까지 이 계좌의 자동 동기화가 중단됩니다.",
};

interface Props {
  accountId: string;
  broker: CredentialBroker;
}

/** 계좌 수정 모달에서 계좌에 저장된 브로커 API 키만 삭제(연동 해제) — 계좌·거래내역은 유지된다. */
export default function CredentialDisconnectButton({ accountId, broker }: Props) {
  const qc = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [disconnected, setDisconnected] = useState(false);
  const label = BROKER_LABELS[broker];

  const mutation = useMutation({
    mutationFn: () => deleteAccountCredentials(accountId, broker),
    onSuccess: () => {
      setDisconnected(true);
      toast(`${label} API 키를 삭제했습니다`, "success");
      void invalidateBrokerCredentialData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "API 키 삭제에 실패했습니다"), "error"),
  });

  if (disconnected) {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        저장된 {label} API 키를 삭제했습니다. 다시 연결하려면 위에 새 키를 입력해 저장하세요.
      </p>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setConfirmOpen(true)}
        disabled={mutation.isPending}
        className={`text-xs text-red-600 dark:text-red-400 hover:underline underline-offset-2 disabled:opacity-50 ${TOUCH_TARGET_MIN_MOBILE_ONLY} justify-start`}
      >
        {mutation.isPending ? "삭제 중..." : `저장된 ${label} API 키 삭제 (연동 해제)`}
      </button>
      {confirmOpen && (
        <ConfirmModal
          message={`이 계좌에 저장된 ${label} API 키를 삭제할까요? 계좌와 거래내역은 그대로 유지됩니다. ${CONSEQUENCE[broker]}`}
          confirmLabel="삭제"
          onConfirm={() => {
            setConfirmOpen(false);
            mutation.mutate();
          }}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </>
  );
}
