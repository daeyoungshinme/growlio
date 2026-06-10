import { useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/authStore";
import { PERSIST_CACHE_KEY } from "@/constants/queryConfig";

export function useLogout() {
  const logout = useAuthStore((s) => s.logout);
  const queryClient = useQueryClient();

  return async () => {
    queryClient.clear();
    window.localStorage.removeItem(PERSIST_CACHE_KEY);
    await logout();
  };
}
