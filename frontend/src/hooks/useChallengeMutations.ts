import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  type ChallengeCreatePayload,
  type ChallengeUpdatePayload,
  createChallenge,
  deleteChallenge,
  updateChallenge,
} from "@/api/challenges";
import { invalidateChallengeData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 적립 챌린지 생성/수정/삭제 뮤테이션 묶음. */
export function useChallengeMutations() {
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: (payload: ChallengeCreatePayload) => createChallenge(payload),
    onSuccess: async () => {
      toast("챌린지가 생성되었습니다", "success");
      await invalidateChallengeData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const update = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ChallengeUpdatePayload }) =>
      updateChallenge(id, payload),
    onSuccess: async () => {
      toast("챌린지가 수정되었습니다", "success");
      await invalidateChallengeData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteChallenge(id),
    onSuccess: async () => {
      toast("챌린지가 삭제되었습니다", "success");
      await invalidateChallengeData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return { create, update, remove };
}
