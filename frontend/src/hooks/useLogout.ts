import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { PERSIST_CACHE_KEY } from "@/constants/queryConfig";
import { storageRemove } from "@/utils/safeStorage";

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const queryClient = useQueryClient();

  return async () => {
    queryClient.clear();
    storageRemove(PERSIST_CACHE_KEY);
    await logout();
  };
}
