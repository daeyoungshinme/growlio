import type { QueryClient } from "@tanstack/react-query";

/** 계좌 sync 후 — portfolio + dashboard + 배당 데이터 */
export function invalidateSyncData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ["portfolio-overview"] }),
    qc.invalidateQueries({ queryKey: ["dashboard"] }),
    qc.invalidateQueries({ queryKey: ["dividend-by-ticker"] }),
    qc.invalidateQueries({ queryKey: ["dividend-summary"] }),
  ]);
}

/** 계좌 CUD 후 — accounts + portfolio + dashboard */
export function invalidateAccountData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ["accounts"] }),
    qc.invalidateQueries({ queryKey: ["portfolio-overview"] }),
    qc.invalidateQueries({ queryKey: ["dashboard"] }),
  ]);
}

/** 거래내역 CUD 후 — transactions + dashboard */
export function invalidateTransactionData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ["transactions"] }),
    qc.invalidateQueries({ queryKey: ["dashboard"] }),
  ]);
}
