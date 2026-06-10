import { useContext, useEffect } from "react";
import { RefreshContext } from "@/components/layout/AppLayout";

/**
 * AppLayout의 pull-to-refresh에 현재 페이지 새로고침 콜백을 등록한다.
 * 페이지가 언마운트되면 자동으로 해제된다.
 */
export function useRegisterRefresh(fn: () => Promise<void>) {
  const { registerRefresh } = useContext(RefreshContext);

  useEffect(() => {
    registerRefresh(fn);
    return () => registerRefresh(null);
  }, [fn, registerRefresh]);
}
