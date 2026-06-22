import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import Tabs from "@/components/common/Tabs";
import PageLoader from "@/components/common/PageLoader";
import { ASSETS_PAGE_SECTIONS, type AssetsPageSectionKey } from "@/constants/tabs";

const AccountManagementContent = lazy(() => import("./AssetManagementPage"));
const PortfolioContent = lazy(() => import("./PortfolioPage"));

const VALID_KEYS = ASSETS_PAGE_SECTIONS.map((s) => s.key);
const LABELS = ASSETS_PAGE_SECTIONS.map((s) => s.label);

export default function AssetsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawSection = searchParams.get("section");
  const sectionKey: AssetsPageSectionKey = VALID_KEYS.includes(rawSection as AssetsPageSectionKey)
    ? (rawSection as AssetsPageSectionKey)
    : "portfolio";

  const activeLabel = ASSETS_PAGE_SECTIONS.find((s) => s.key === sectionKey)!.label;

  const handleSectionChange = (label: string) => {
    const section = ASSETS_PAGE_SECTIONS.find((s) => s.label === label);
    if (section) setSearchParams({ section: section.key }, { replace: true });
  };

  return (
    <div>
      <Tabs
        tabs={LABELS}
        activeTab={activeLabel}
        onChange={handleSectionChange}
        variant="pill"
        className="mb-6"
      />
      {sectionKey === "management" && (
        <Suspense fallback={<PageLoader />}>
          <AccountManagementContent />
        </Suspense>
      )}
      {sectionKey === "portfolio" && (
        <Suspense fallback={<PageLoader />}>
          <PortfolioContent />
        </Suspense>
      )}
    </div>
  );
}
