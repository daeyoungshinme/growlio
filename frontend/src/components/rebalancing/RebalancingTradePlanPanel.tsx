import { useState } from "react";
import { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";
import { CASH_EQUIVALENT_TICKER, CASH_TICKER } from "@/constants/assets";
import { TRADING_FEE_RATE, calcTradeKrw } from "./rebalancingTradeMath";

interface Props {
  items: RebalancingItem[];
  // 요약 카드와 동일한 기준(diff_krw 부호)으로 계산된 총액 — "합계"/수수료 표기에 사용
  totalBuySummary: number;
  totalSellSummary: number;
}

// 종목별 실제 거래 계획 패널 — 매도 먼저, 매수 나중 (모바일 카드 뷰 / 데스크탑 테이블 뷰)
export default function RebalancingTradePlanPanel({
  items,
  totalBuySummary,
  totalSellSummary,
}: Props) {
  const [showTradePlan, setShowTradePlan] = useState(false);

  const buyItems = items.filter(
    (i) => i.shares_to_trade !== null && i.shares_to_trade > 0 && i.current_price_krw,
  );
  const sellItems = items.filter(
    (i) => i.shares_to_trade !== null && i.shares_to_trade < 0 && i.current_price_krw,
  );
  const unpricedItems = items.filter(
    (i) =>
      i.diff_krw !== 0 &&
      (i.shares_to_trade === null || !i.current_price_krw) &&
      i.ticker !== CASH_TICKER &&
      i.ticker !== CASH_EQUIVALENT_TICKER,
  );

  const estFee = (totalBuySummary + totalSellSummary) * TRADING_FEE_RATE;

  if (buyItems.length === 0 && sellItems.length === 0) return null;

  return (
    <div className="rounded-xl bg-gray-800/60 border border-gray-700/50 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium text-gray-300">종목별 거래 계획</div>
        <button
          onClick={() => setShowTradePlan((v) => !v)}
          className="sm:hidden text-xs text-gray-500 hover:text-gray-300 transition-colors"
          aria-expanded={showTradePlan}
          aria-label="종목별 거래 계획 상세"
        >
          {showTradePlan ? "▲ 접기" : "▼ 상세 보기"}
        </button>
      </div>

      {/* 모바일: 카드 뷰 (접기/펼치기) */}
      <div className={`sm:hidden space-y-2 ${showTradePlan ? "block" : "hidden"}`}>
        {sellItems.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-blue-400 font-medium">매도</div>
            {sellItems.map((item, idx) => (
              <div key={idx} className="flex items-start justify-between gap-2 text-xs">
                <div className="min-w-0 flex-1">
                  <div className="text-gray-200 font-medium truncate">{item.name}</div>
                  <div className="text-gray-500 mt-0.5">
                    {Math.abs(Math.round(item.shares_to_trade!))}주 ×{" "}
                    {fmtKrw(item.current_price_krw!)}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className={`font-medium ${LOSS_COLOR}`}>{fmtKrw(calcTradeKrw(item))}</div>
                  <div className="text-gray-500 mt-0.5">
                    수수료 {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}
                  </div>
                </div>
              </div>
            ))}
            {sellItems.length > 1 && (
              <div className="flex justify-between text-xs pt-1 border-t border-gray-700/40">
                <span className="text-gray-500">매도 합계</span>
                <span className={`font-medium ${LOSS_COLOR}`}>{fmtKrw(totalSellSummary)}</span>
              </div>
            )}
          </div>
        )}
        {buyItems.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-green-400 font-medium">매수</div>
            {buyItems.map((item, idx) => (
              <div key={idx} className="flex items-start justify-between gap-2 text-xs">
                <div className="min-w-0 flex-1">
                  <div className="text-gray-200 font-medium truncate">{item.name}</div>
                  <div className="text-gray-500 mt-0.5">
                    {Math.abs(Math.round(item.shares_to_trade!))}주 ×{" "}
                    {fmtKrw(item.current_price_krw!)}
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <div className={`font-medium ${PROFIT_COLOR}`}>{fmtKrw(calcTradeKrw(item))}</div>
                  <div className="text-gray-500 mt-0.5">
                    수수료 {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}
                  </div>
                </div>
              </div>
            ))}
            {buyItems.length > 1 && (
              <div className="flex justify-between text-xs pt-1 border-t border-gray-700/40">
                <span className="text-gray-500">매수 합계</span>
                <span className={`font-medium ${PROFIT_COLOR}`}>{fmtKrw(totalBuySummary)}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 데스크탑: 테이블 뷰 (배분 예산 컬럼 제거 → 4열) */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-700/50 text-gray-500">
              <th className="text-left py-1.5 pr-3 font-medium">종목</th>
              <th className="text-right py-1.5 px-3 font-medium">현재가</th>
              <th className="text-right py-1.5 px-3 font-medium">수량</th>
              <th className="text-right py-1.5 px-3 font-medium">실제금액</th>
              <th className="text-right py-1.5 pl-3 font-medium">수수료</th>
            </tr>
          </thead>
          <tbody>
            {sellItems.length > 0 && (
              <>
                <tr>
                  <td colSpan={5} className="pt-2 pb-1 text-blue-400 font-medium">
                    매도
                  </td>
                </tr>
                {sellItems.map((item, idx) => (
                  <tr key={idx} className="border-b border-gray-700/30">
                    <td className="py-1.5 pr-3 text-gray-200 truncate max-w-[140px]">
                      {item.name}
                    </td>
                    <td className="py-1.5 px-3 text-right text-gray-400">
                      {fmtKrw(item.current_price_krw!)}
                    </td>
                    <td className="py-1.5 px-3 text-right text-gray-200">
                      {Math.abs(Math.round(item.shares_to_trade!))}주
                    </td>
                    <td className={`py-1.5 px-3 text-right font-medium ${LOSS_COLOR}`}>
                      {fmtKrw(calcTradeKrw(item))}
                    </td>
                    <td className="py-1.5 pl-3 text-right text-gray-500">
                      {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}
                    </td>
                  </tr>
                ))}
              </>
            )}
            {buyItems.length > 0 && (
              <>
                <tr>
                  <td colSpan={5} className="pt-2 pb-1 text-green-400 font-medium">
                    매수
                  </td>
                </tr>
                {buyItems.map((item, idx) => (
                  <tr key={idx} className="border-b border-gray-700/30">
                    <td className="py-1.5 pr-3 text-gray-200 truncate max-w-[140px]">
                      {item.name}
                    </td>
                    <td className="py-1.5 px-3 text-right text-gray-400">
                      {fmtKrw(item.current_price_krw!)}
                    </td>
                    <td className="py-1.5 px-3 text-right text-gray-200">
                      {Math.abs(Math.round(item.shares_to_trade!))}주
                    </td>
                    <td className={`py-1.5 px-3 text-right font-medium ${PROFIT_COLOR}`}>
                      {fmtKrw(calcTradeKrw(item))}
                    </td>
                    <td className="py-1.5 pl-3 text-right text-gray-500">
                      {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}
                    </td>
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {/* 예상 거래 비용 합계 */}
      {estFee > 0 && (
        <div className="flex items-center justify-between text-xs border-t border-gray-700/40 pt-2.5">
          <span className="text-gray-400">
            예상 거래 비용 <span className="text-gray-500">(수수료 0.014%)</span>
          </span>
          <span className="text-gray-300 font-medium">{fmtKrw(estFee)}</span>
        </div>
      )}

      {/* 현재가 미조회로 거래 계획에서 제외된 종목 안내 */}
      {unpricedItems.length > 0 && (
        <div className="text-xs text-amber-500/80 pt-1">
          {unpricedItems.map((i) => i.name).join(", ")} 등 {unpricedItems.length}개 종목은 현재가
          미조회로 거래 계획에서 제외됨
        </div>
      )}
    </div>
  );
}
