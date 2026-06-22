import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import Tabs from "@/components/common/Tabs";
import PageLoader from "@/components/common/PageLoader";
import { ASSETS_PAGE_SECTIONS, type AssetsPageSection } from "@/constants/tabs";

const AccountManagementContent = lazy(() => import("./AssetManagementPage"));
const PortfolioContent = lazy(() => import("./PortfolioPage"));

export default function AssetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawSection = searchParams.get("section");
  const section: AssetsPageSection = ASSETS_PAGE_SECTIONS.includes(rawSection as AssetsPageSection)
    ? (rawSection as AssetsPageSection)
    : "투자 현황";

  const handleSectionChange = (next: AssetsPageSection) => {
    setSearchParams({ section: next }, { replace: true });
  };

  return (
    <div>
      <Tabs
        tabs={ASSETS_PAGE_SECTIONS}
        activeTab={section}
        onChange={handleSectionChange}
        variant="pill"
        className="mb-6"
      />
      {section === "계좌 관리" && (
        <Suspense fallback={<PageLoader />}>
          <AccountManagementContent />
        </Suspense>
      )}
      {section === "투자 현황" && (
        <Suspense fallback={<PageLoader />}>
          <PortfolioContent />
        </Suspense>
      )}
    </div>
  );
}
