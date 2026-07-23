import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { fetchSettings, type SettingsData } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

type BooleanSettingsField = {
  [K in keyof SettingsData]: SettingsData[K] extends boolean ? K : never;
}[keyof SettingsData];

interface UseSettingsToggleOptions {
  field: BooleanSettingsField;
  defaultValue: boolean;
  mutationFn: (enabled: boolean) => Promise<unknown>;
  invalidate: (qc: QueryClient) => unknown;
}

/** `["settings"]`의 boolean 필드 하나를 조회하고 PUT으로 토글하는 반복 패턴(조회+뮤테이션+무효화+에러토스트)을
 * 통합한 제네릭 팩토리. 옵트인 알림 토글 훅(`useGoalAchievementAlertsToggle` 등)이 이 위에서 필드명만 다르게 얹는다. */
export function useSettingsToggle({
  field,
  defaultValue,
  mutationFn,
  invalidate,
}: UseSettingsToggleOptions) {
  const qc = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn,
    onSuccess: () => {
      void invalidate(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return {
    enabled: settings?.[field] ?? defaultValue,
    toggle: (enabled: boolean) => toggleMut.mutate(enabled),
    isPending: toggleMut.isPending,
  };
}
