import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { SELECT_SM } from "@/constants/inputStyles";
import { isStockAccount } from "@/utils/accounts";
import Tabs from "@/components/common/Tabs";
import TaxLimitsSection from "@/components/portfolio-analysis/TaxLimitsSection";
import TaxOptimizationCard from "@/components/portfolio-analysis/TaxOptimizationCard";

const TAX_TABS = ["한도 현황", "세금 추정"] as const;
type TaxTab = (typeof TAX_TABS)[number];

/** 계획 › 절세 탭 — "한도 현황"(절세 액션 플랜·ISA 만기·연금 공제한도)과 "세금 추정"(배당세·해외 양도세 +
 * 절세 플래너/금투세 시뮬레이션)을 탭으로 묶는다. 2026-10-08(plans/50 M1) 자산 › 투자현황 › 세금에서 이동 —
 * 요구사항상 "절세 계획"이라 계획 탭이 제자리이고, 자산 탭 중첩이 한 단 준다. 옛 링크(`?portfolioTab=세금`)는
 * `AssetsPage`가 이 탭으로 리다이렉트한다(`utils/legacyTabRedirect`).
 *
 * "세금 추정"의 계좌 필터는 예전엔 투자현황 상단 계좌 선택(`?account=`)을 따랐으나, 이제 자체 선택(`?taxAccount=`)을 갖는다. */
export default function TaxTabContainer() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTaxTab = searchParams.get("taxTab");
  const taxTab: TaxTab = (TAX_TABS as readonly string[]).includes(rawTaxTab ?? "")
    ? (rawTaxTab as TaxTab)
    : "한도 현황";
  const accountId = searchParams.get("taxAccount") || null;

  const setParam = useCallback(
    (key: string, value: string | null) => {
      setSearchParams(
        (prev) => {
          if (value) prev.set(key, value);
          else prev.delete(key);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const { data: accountsList } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.LONG,
    enabled: taxTab === "세금 추정",
  });
  const stockAccounts = useMemo(
    () => (accountsList ?? []).filter((a) => isStockAccount(a.asset_type)),
    [accountsList],
  );

  return (
    <div className="space-y-4">
      <Tabs
        tabs={TAX_TABS}
        activeTab={taxTab}
        onChange={(next) => setParam("taxTab", next)}
        variant="underline"
      />
      {taxTab === "한도 현황" && <TaxLimitsSection />}
      {taxTab === "세금 추정" && (
        <>
          {stockAccounts.length > 1 && (
            <select
              value={accountId ?? ""}
              onChange={(e) => setParam("taxAccount", e.target.value || null)}
              className={`${SELECT_SM} w-full sm:w-auto`}
              aria-label="세금 추정 계좌 선택"
            >
              <option value="">전체 계좌 ({stockAccounts.length}개)</option>
              {stockAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          )}
          <TaxOptimizationCard accountId={accountId} />
        </>
      )}
    </div>
  );
}
