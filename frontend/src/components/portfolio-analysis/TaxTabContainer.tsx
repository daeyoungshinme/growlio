import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import Tabs from "@/components/common/Tabs";
import TaxLimitsSection from "@/components/portfolio-analysis/TaxLimitsSection";
import TaxOptimizationCard from "@/components/portfolio-analysis/TaxOptimizationCard";

const TAX_TABS = ["한도 현황", "세금 추정"] as const;
type TaxTab = (typeof TAX_TABS)[number];

interface Props {
  /** 특정 계좌만 필터링해 조회 (미지정 시 전체 계좌 통합) — "세금 추정" 탭에만 적용된다. */
  accountId?: string | null;
}

/** 자산탭 세금 서브탭 — "한도 현황"(ISA 만기·연금 공제한도)과 "세금 추정"(배당세·해외 양도세 +
 * 절세 플래너/금투세 시뮬레이션)을 탭으로 묶는다. 기존에는 두 카드가 각각 접기 카드로 쌓여 3중
 * 중첩(세금 서브탭 → 카드 펼치기 → 카드 내부 섹션 펼치기)이었던 것을 탭 전환 1단계로 단순화
 * (2026-07-25 세금정보 3곳→2곳 통합). Home 배너(`TaxLimitsBanner`)의 `?portfolioTab=세금` 딥링크는
 * 기본 탭("한도 현황")으로 랜딩해 배너가 요약하는 내용과 자연스럽게 일치한다. */
export default function TaxTabContainer({ accountId }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTaxTab = searchParams.get("taxTab");
  const taxTab: TaxTab = (TAX_TABS as readonly string[]).includes(rawTaxTab ?? "")
    ? (rawTaxTab as TaxTab)
    : "한도 현황";

  const handleTaxTabChange = useCallback(
    (next: TaxTab) => {
      setSearchParams(
        (prev) => {
          prev.set("taxTab", next);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  return (
    <div className="space-y-4">
      <Tabs tabs={TAX_TABS} activeTab={taxTab} onChange={handleTaxTabChange} variant="pill" />
      {taxTab === "한도 현황" && <TaxLimitsSection />}
      {taxTab === "세금 추정" && <TaxOptimizationCard accountId={accountId} />}
    </div>
  );
}
