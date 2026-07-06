import { create } from "zustand";
import type { PortfolioItem } from "@/api/portfolios";

interface PendingRecommendation {
  portfolioId: string;
  items: PortfolioItem[];
}

interface PendingRecommendationState {
  pending: PendingRecommendation | null;
  setPending: (portfolioId: string, items: PortfolioItem[]) => void;
  clearPending: () => void;
}

/** 목표 역산 추천(GoalRecommendationCard)의 "적용" 클릭을 같은 탭 내 다른 컴포넌트(PortfolioManageTab)의
 * 포트폴리오 편집기로 전달하는 임시 브리지. 편집기가 값을 소비하면 즉시 clearPending한다. */
export const usePendingRecommendationStore = create<PendingRecommendationState>((set) => ({
  pending: null,
  setPending: (portfolioId, items) => set({ pending: { portfolioId, items } }),
  clearPending: () => set({ pending: null }),
}));
