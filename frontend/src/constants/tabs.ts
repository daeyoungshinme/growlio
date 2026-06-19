export const ASSET_MANAGEMENT_TABS = ["은행계좌", "증권계좌", "부동산", "입출금·배당"] as const;
export type AssetManagementTab = (typeof ASSET_MANAGEMENT_TABS)[number];

export const PORTFOLIO_TABS = ["종목 현황", "배당", "세금", "진단"] as const;
export type PortfolioTab = (typeof PORTFOLIO_TABS)[number];
