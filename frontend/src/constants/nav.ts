import { BarChart2, Home, Settings, Shuffle, TrendingUp, Wallet } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  icon: LucideIcon;
  label: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", icon: Home, label: "대시보드" },
  { to: "/assets", icon: Wallet, label: "자산" },
  { to: "/rebalancing", icon: Shuffle, label: "리밸런싱" },
  { to: "/invest-plan", icon: TrendingUp, label: "투자 계획" },
  { to: "/market", icon: BarChart2, label: "시장" },
  { to: "/settings", icon: Settings, label: "설정" },
];
