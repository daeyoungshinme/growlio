import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

interface UseAlertCrudOptions<TItem> {
  queryKey: readonly unknown[];
  queryFn: () => Promise<TItem[]>;
  reactivateFn: (id: string) => Promise<unknown>;
  deleteFn: (id: string) => Promise<unknown>;
  invalidateFn: (qc: QueryClient) => void;
}

export function useAlertCrud<TItem>({
  queryKey,
  queryFn,
  reactivateFn,
  deleteFn,
  invalidateFn,
}: UseAlertCrudOptions<TItem>) {
  const qc = useQueryClient();

  const { data: items = [] as TItem[] } = useQuery<TItem[]>({ queryKey, queryFn });

  const reactivateMutation = useMutation({
    mutationFn: reactivateFn,
    onSuccess: () => {
      invalidateFn(qc);
      toast("알림이 재활성화되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "재활성화에 실패했습니다"), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteFn,
    onSuccess: () => invalidateFn(qc),
    onError: (e) => toast(extractErrorMessage(e, "알림 삭제에 실패했습니다"), "error"),
  });

  return { items, reactivateMutation, deleteMutation };
}
