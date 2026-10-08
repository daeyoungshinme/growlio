import { lazy, Suspense, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import TransactionHistoryTab from "@/components/assets/TransactionHistoryTab";
import type { AssetAccount } from "@/api/assets";

const PeriodPurchasesTab = lazy(() => import("@/components/assets/PeriodPurchasesTab"));

const HISTORY_SEGMENTS = ["현금 흐름", "매수 내역"] as const;
type HistorySegment = (typeof HISTORY_SEGMENTS)[number];

/** 자산 › 계좌관리 › 내역 — 입출금·배당(현금 흐름)과 기간별 매수(매수 내역)를 한 탭의 세그먼트로 묶는다
 * (plans/50 M2). 둘 다 계좌 CRUD가 아닌 "기록" 화면이라 하위탭 2개를 차지할 이유가 없었고, 360px에서
 * 계좌관리 하위탭 5개가 넘치던 문제도 함께 해소된다. 세그먼트는 `?history=`로 영속. */
export default function AccountHistoryTab({ accounts }: { accounts: AssetAccount[] }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("history");
  const segment: HistorySegment = (HISTORY_SEGMENTS as readonly string[]).includes(raw ?? "")
    ? (raw as HistorySegment)
    : "현금 흐름";
  const setSegment = useCallback(
    (next: HistorySegment) =>
      setSearchParams(
        (prev) => {
          prev.set("history", next);
          return prev;
        },
        { replace: true },
      ),
    [setSearchParams],
  );

  return (
    <div className="space-y-4">
      <Tabs
        tabs={HISTORY_SEGMENTS}
        activeTab={segment}
        onChange={setSegment}
        variant="pill"
        fullWidth
      />
      {segment === "현금 흐름" ? (
        <TransactionHistoryTab accounts={accounts} />
      ) : (
        <Suspense fallback={<SkeletonCard rows={3} />}>
          <PeriodPurchasesTab accounts={accounts} />
        </Suspense>
      )}
    </div>
  );
}
