import type { OrderResult } from "../../api/rebalancing";

export function SideBadge({ isBuy }: { isBuy: boolean }) {
  return (
    <span className={`font-medium text-xs ${isBuy ? "text-red-400" : "text-blue-400"}`}>
      {isBuy ? "매수" : "매도"}
    </span>
  );
}

export function StatusBadge({ status }: { status: OrderResult["status"] }) {
  if (status === "SUCCESS")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-900/30 text-green-400">
        성공
      </span>
    );
  if (status === "FAILED")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-900/30 text-red-400">
        실패
      </span>
    );
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-700 text-gray-400">
      건너뜀
    </span>
  );
}
