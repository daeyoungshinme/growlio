import { Home, Settings, Shuffle, TrendingUp, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", icon: Home, label: "홈" },
  { to: "/assets", icon: Wallet, label: "자산" },
  { to: "/rebalancing", icon: Shuffle, label: "리밸런싱" },
  { to: "/invest-plan", icon: TrendingUp, label: "계획" },
  { to: "/settings", icon: Settings, label: "설정" },
];

/** 하단 네비 경로 순서 — `NAV_ITEMS`에서 파생. 페이지 간 스와이프 전환(`useSwipeNavigation`)에서 사용 */
export const NAV_ORDER: string[] = NAV_ITEMS.map((item) => item.to);
