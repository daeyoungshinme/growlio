import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import PageLoader from "@/components/common/PageLoader";
import Tabs from "@/components/common/Tabs";
import { ASSETS_TOP_TABS, type AssetsTopTab } from "@/constants/tabs";

const AssetManagementContent = lazy(() => import("./AssetManagementPage"));
const PortfolioContent = lazy(() => import("./PortfolioPage"));

export default function AssetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab: AssetsTopTab =
    (ASSETS_TOP_TABS as readonly string[]).includes(rawTab ?? "")
      ? (rawTab as AssetsTopTab)
      : "계좌관리";

  const handleTabChange = (tab: AssetsTopTab) => {
    setSearchParams((prev) => {
      prev.set("tab", tab);
      if (tab !== "투자현황") prev.delete("portfolioTab");
      return prev;
    }, { replace: true });
  };

  return (
    <div>
      <Tabs
        tabs={ASSETS_TOP_TABS}
        activeTab={activeTab}
        onChange={handleTabChange}
        variant="pill"
        className="mb-6"
      />
      <Suspense fallback={<PageLoader />}>
        {activeTab === "투자현황" ? <PortfolioContent /> : <AssetManagementContent />}
      </Suspense>
    </div>
  );
}
