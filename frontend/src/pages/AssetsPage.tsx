import { lazy, Suspense, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import PageLoader from "@/components/common/PageLoader";
import Tabs from "@/components/common/Tabs";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { ASSETS_TOP_TABS, type AssetsTopTab } from "@/constants/tabs";

const AssetManagementContent = lazy(() => import("./AssetManagementPage"));
const PortfolioContent = lazy(() => import("./PortfolioPage"));

export default function AssetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab: AssetsTopTab = (ASSETS_TOP_TABS as readonly string[]).includes(rawTab ?? "")
    ? (rawTab as AssetsTopTab)
    : "투자현황";

  const handleTabChange = (tab: AssetsTopTab) => {
    setSearchParams(
      (prev) => {
        prev.set("tab", tab);
        if (tab !== "투자현황") prev.delete("portfolioTab");
        return prev;
      },
      { replace: true },
    );
  };

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, ASSETS_TOP_TABS, activeTab, handleTabChange);

  return (
    <div>
      <h1 className="sr-only">자산</h1>
      <Tabs
        tabs={ASSETS_TOP_TABS}
        activeTab={activeTab}
        onChange={handleTabChange}
        variant="pill"
        className="mb-6"
      />
      <div ref={tabContentRef}>
        <Suspense fallback={<PageLoader />}>
          {activeTab === "투자현황" ? <PortfolioContent /> : <AssetManagementContent />}
        </Suspense>
      </div>
    </div>
  );
}
