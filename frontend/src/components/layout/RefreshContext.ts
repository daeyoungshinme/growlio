import { createContext } from "react";

// 페이지 컴포넌트가 새로고침 콜백을 AppLayout에 등록하기 위한 컨텍스트
export interface RefreshContextValue {
  registerRefresh: (fn: (() => Promise<void>) | null) => void;
}

export const RefreshContext = createContext<RefreshContextValue>({
  registerRefresh: () => {},
});
