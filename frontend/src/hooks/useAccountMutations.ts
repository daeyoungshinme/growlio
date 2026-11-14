import { useCallback, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { createAccount, updateAccount, deleteAccount, syncAccount } from "@/api/assets";
import { extractErrorMessage, getHttpStatus } from "@/utils/error";
import {
  invalidateAccountData,
  invalidateBrokerCredentialData,
  invalidateAccountListData,
  invalidateSyncData,
} from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { STOCK_TYPE_LABELS } from "@/constants";
import { isSyncableAccount } from "@/utils/accounts";

interface Options {
  onBankModalClose: () => void;
  onStockModalClose: () => void;
  onEditBankClose: () => void;
  onEditRealEstateClose: () => void;
  onEditStockClose: () => void;
}

export function useAccountMutations({
  onBankModalClose,
  onStockModalClose,
  onEditBankClose,
  onEditRealEstateClose,
  onEditStockClose,
}: Options) {
  const queryClient = useQueryClient();
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncingStockIds, setSyncingStockIds] = useState<Set<string>>(new Set());

  const invalidateAll = useCallback(() => invalidateAccountData(queryClient), [queryClient]);

  const createMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async (data) => {
      const syncable = isSyncableAccount(data.data_source);
      // 동기화할 계좌는 첫 sync 뒤에 한 번만 전체 무효화한다 — 그 전엔 목록만(plans/125 D3)
      void (syncable ? invalidateAccountListData(queryClient) : invalidateAll());
      onBankModalClose();
      onStockModalClose();
      if (syncable) {
        setSyncingStockIds((prev) => new Set(prev).add(data.id));
        try {
          await syncAccount(data.id);
          // 첫 sync로 보유 종목이 생기므로 계좌 CUD 범위(보유 기반 + 거래·연금 납입) 전체를 무효화
          void invalidateAll();
          toast("계좌가 추가되었습니다", "success");
        } catch (e) {
          void invalidateAll();
          const fallback = "초기 동기화 실패. 계좌 카드의 동기화 버튼으로 재시도하세요.";
          toast(getHttpStatus(e) != null ? extractErrorMessage(e, fallback) : fallback);
        } finally {
          setSyncingStockIds((prev) => {
            const next = new Set(prev);
            next.delete(data.id);
            return next;
          });
        }
      } else {
        toast("계좌가 추가되었습니다", "success");
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 추가에 실패했습니다"), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      // 삭제는 서버가 그 계좌의 자동 실행 알림을 끄고 대기 매수를 취소한다 — 알림·대기 플랜도 다시 받는다
      void invalidateBrokerCredentialData(queryClient);
      setDeletingId(null);
      toast("계좌가 삭제되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 삭제에 실패했습니다"), "error"),
  });

  const updateBankMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => {
      void invalidateAll();
      onEditBankClose();
      toast("저장되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 수정에 실패했습니다"), "error"),
  });

  const updateDepositMutation = useMutation({
    mutationFn: ({
      id,
      deposit_krw,
      deposit_usd,
    }: {
      id: string;
      deposit_krw: number;
      deposit_usd?: number;
    }) => updateAccount(id, { deposit_krw, ...(deposit_usd !== undefined ? { deposit_usd } : {}) }),
    onSuccess: () => {
      void invalidateAll();
      toast("예수금이 업데이트되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "예수금 수정에 실패했습니다"), "error"),
  });

  const updateNameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => updateAccount(id, { name }),
    onSuccess: () => {
      void invalidateAll();
      toast("계좌명이 저장되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌명 수정에 실패했습니다"), "error"),
  });

  const updateStockMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => {
      void invalidateAll();
      onEditStockClose();
      toast("저장되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 수정에 실패했습니다"), "error"),
  });

  const updateRealEstateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => {
      void invalidateAll();
      onEditRealEstateClose();
      toast("저장되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "부동산 정보 수정에 실패했습니다"), "error"),
  });

  const handleSyncKisAccount = useCallback(
    async (id: string, accounts: AssetAccount[]) => {
      const acc = accounts.find((a) => a.id === id);
      setSyncingStockIds((prev) => new Set(prev).add(id));
      try {
        await syncAccount(id);
        await invalidateSyncData(queryClient);
        toast("동기화 완료", "success");
      } catch (e) {
        void invalidateSyncData(queryClient);
        const broker = acc ? (STOCK_TYPE_LABELS[acc.asset_type] ?? "증권사") : "증권사";
        const fallback = `동기화 실패. ${broker} API 자격증명을 확인하세요.`;
        toast(getHttpStatus(e) != null ? extractErrorMessage(e, fallback) : fallback);
      } finally {
        setSyncingStockIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      }
    },
    [queryClient],
  );

  return {
    createMutation,
    deleteMutation,
    updateBankMutation,
    updateStockMutation,
    updateDepositMutation,
    updateNameMutation,
    updateRealEstateMutation,
    handleSyncKisAccount,
    deletingId,
    setDeletingId,
    syncingStockIds,
    invalidateAll,
  };
}
