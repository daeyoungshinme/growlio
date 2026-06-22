import { useState } from "react";
import { ExecutionResult, RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";
import { RebalancingExecutionModal } from "./RebalancingExecutionModal";
import ErrorBoundary from "@/components/ErrorBoundary";
import {
  CagrCard,
  DiffCell,
  QuantityCell,
  Return10yCell,
  WeightBar,
  WeightDiffBadge,
} from "./RebalancingCells";
import RebalancingDividendSection from "./RebalancingDividendSection";
import { CASH_TICKER } from "@/constants/assets";
import RebalancingDiagnosisCard from "./RebalancingDiagnosisCard";

const TRADING_FEE_RATE = 0.00014; // 0.014% 수수료 (한국투자증권 기준)

// 반올림된 주수 기준 실제 거래금액 — 요약·거래계획·거래비용 전체에서 동일하게 사용
function calcTradeKrw(item: RebalancingItem): number {
  if (item.shares_to_trade !== null && item.current_price_krw && item.current_price_krw > 0) {
    return Math.abs(Math.round(item.shares_to_trade)) * item.current_price_krw;
  }
  return Math.abs(item.diff_krw);
}

// 부호 포함 실제 거래금액 — 상세내역 DiffCell과 거래 계획 금액을 일치시키기 위해 사용
function calcSignedTradeKrw(item: RebalancingItem): number {
  if (item.shares_to_trade !== null && item.current_price_krw && item.current_price_krw > 0) {
    return Math.sign(item.diff_krw) * Math.abs(Math.round(item.shares_to_trade)) * item.current_price_krw;
  }
  return item.diff_krw;
}

// ─── 테이블 행 컴포넌트 ────────────────────────────────────────────────────────

function RebalancingItemMobileCard({ item }: { item: RebalancingItem }) {
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  const weightDiff = item.weight_diff_pct;
  const directionIcon = weightDiff > 0 ? "↑" : weightDiff < 0 ? "↓" : "";
  return (
    <div className="py-3 px-1">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="font-medium text-gray-100 truncate text-sm">{item.name}</p>
            {isUntracked && <span className="text-xs text-amber-500 shrink-0">목표 외</span>}
            {directionIcon && (
              <span className={`text-xs shrink-0 ${weightDiff > 0 ? "text-red-400" : "text-blue-400"}`}>
                {directionIcon}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400">
            {item.ticker} · 현재 {item.current_weight_pct.toFixed(1)}%
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className="text-xs text-gray-500">목표 {item.target_weight_pct.toFixed(1)}%</div>
          <DiffCell diff={calcSignedTradeKrw(item)} />
          <p className="text-xs text-gray-400 mt-0.5">
            <QuantityCell item={item} />
          </p>
        </div>
      </div>
      <div className="mt-2">
        <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
      </div>
      <div className="mt-1.5">
        <WeightDiffBadge diff={item.weight_diff_pct} />
      </div>
    </div>
  );
}

function RebalancingItemRow({ item }: { item: RebalancingItem }) {
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  return (
    <tr className="border-b border-gray-700 hover:bg-gray-700 group">
      <td className="py-3.5 px-3 sticky left-0 bg-gray-900 group-hover:bg-gray-700 transition-colors">
        <div className="font-medium text-gray-100 truncate max-w-[160px]">{item.name}</div>
        <div className="text-xs text-gray-400">{item.ticker}</div>
        {isUntracked && <div className="text-xs text-amber-500 mt-0.5">목표 외</div>}
      </td>
      <td className="py-3.5 px-3 text-right text-gray-300">
        {item.current_weight_pct.toFixed(1)}%
      </td>
      <td className="py-3.5 px-3">
        <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <WeightDiffBadge diff={item.weight_diff_pct} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <div className="text-xs text-gray-300">{fmtKrw(item.current_value_krw)}</div>
        <div className="text-xs text-gray-500">→ {fmtKrw(item.target_value_krw)}</div>
      </td>
      <td className="py-3.5 px-3 text-right">
        <DiffCell diff={calcSignedTradeKrw(item)} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <QuantityCell item={item} />
      </td>
      <td className="py-3.5 px-3">
        <Return10yCell item={item} />
      </td>
    </tr>
  );
}

// ─── 메인 컴포넌트 ──────────────────────────────────────────────────────────────

interface Props {
  analysis: RebalancingAnalysis;
  portfolioId: string;
  accounts: AssetAccount[];
  alertThreshold?: number;
  onExecuted?: (results: ExecutionResult[]) => void;
}

export default function RebalancingTable({
  analysis,
  portfolioId,
  accounts,
  alertThreshold,
  onExecuted,
}: Props) {
  const kisAccounts = accounts.filter(
    (a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM",
  );
  const [executionOpen, setExecutionOpen] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [showTradePlan, setShowTradePlan] = useState(false);

  const [now] = useState(() => Date.now());
  const minutesOld = (now - new Date(analysis.analyzed_at).getTime()) / 60000;
  const isStale = minutesOld > 10;

  const hasDividendData =
    (analysis.target_portfolio_annual_dividend ?? 0) > 0 ||
    (analysis.total_current_annual_dividend ?? analysis.current_portfolio_annual_dividend ?? 0) > 0;
  const hasCagrData =
    analysis.target_weighted_cagr_10y_pct != null || analysis.current_weighted_cagr_10y_pct != null;

  // 요약·거래계획·거래비용 모두 calcTradeKrw 기준으로 통일
  const totalBuySummary = analysis.items
    .filter((i) => i.diff_krw > 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const totalSellSummary = analysis.items
    .filter((i) => i.diff_krw < 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const cashAvailable = analysis.available_cash_krw ?? 0;
  const cashAfter = cashAvailable + totalSellSummary - totalBuySummary;
  const estFee = (totalBuySummary + totalSellSummary) * TRADING_FEE_RATE;
  const cashAfterCls =
    cashAfter >= 0
      ? cashAfter < totalBuySummary * 0.05
        ? "text-amber-400"
        : "text-green-400"
      : "text-red-400";

  // 거래 계획 목록: 현재가 있는 종목만
  const buyItems = analysis.items.filter(
    (i) => i.shares_to_trade !== null && i.shares_to_trade > 0 && i.current_price_krw,
  );
  const sellItems = analysis.items.filter(
    (i) => i.shares_to_trade !== null && i.shares_to_trade < 0 && i.current_price_krw,
  );
  // 현재가 미조회로 거래 계획에서 제외된 종목
  const unpricedItems = analysis.items.filter(
    (i) =>
      i.diff_krw !== 0 &&
      (i.shares_to_trade === null || !i.current_price_krw) &&
      i.ticker !== CASH_TICKER,
  );

  return (
    <div className="space-y-4">
      {/* 리밸런싱 진단 요약 카드 */}
      <RebalancingDiagnosisCard
        analysis={analysis}
        alertThreshold={alertThreshold}
        onExecute={kisAccounts.length > 0 ? () => setExecutionOpen(true) : undefined}
      />

      {/* 실행 버튼 행 (데스크탑) */}
      <div className="hidden sm:flex items-center gap-2">
        {isStale && (
          <span className="text-xs text-amber-400 bg-amber-900/30 border border-amber-700/40 rounded-lg px-2.5 py-1">
            분석 {Math.floor(minutesOld)}분 경과 — 재분석 권장
          </span>
        )}
        <div className="flex items-center gap-2 ml-auto">
          {kisAccounts.length === 0 && (
            <span className="text-xs text-gray-500">
              KIS 증권계좌 연동 시 자동 주문 가능
            </span>
          )}
          <button
            onClick={() => setExecutionOpen(true)}
            disabled={kisAccounts.length === 0}
            className="inline-flex bg-indigo-600 text-white px-4 py-1.5 text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
          >
            ⚡ 리밸런싱 실행
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="space-y-2">
        {/* 핵심 요약 — 2×2 그리드 */}
        <div
          className={`rounded-xl p-3 ${cashAfter < 0 ? "bg-red-900/20 border border-red-800/40" : "bg-gray-700/60"}`}
        >
          <div className="text-xs text-gray-500 mb-2">
            {analysis.base_type === "STOCK_ONLY"
              ? cashAvailable > 0
                ? `기준 자산 ${fmtKrw(analysis.base_value_krw)} (주식+예수금)`
                : `기준 자산 ${fmtKrw(analysis.base_value_krw)}`
              : `기준 자산 ${fmtKrw(analysis.base_value_krw)} (전체)`}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-gray-800/60 rounded-lg p-2">
              <div className="text-xs text-gray-500 mb-0.5">예수금</div>
              <div className="text-sm font-semibold text-gray-200">{fmtKrw(cashAvailable)}</div>
            </div>
            <div className="bg-gray-800/60 rounded-lg p-2">
              <div className="text-xs text-gray-500 mb-0.5">매도 예상</div>
              <div className={`text-sm font-semibold ${totalSellSummary > 0 ? LOSS_COLOR : "text-gray-400"}`}>
                {totalSellSummary > 0 ? `+${fmtKrw(totalSellSummary)}` : "—"}
              </div>
            </div>
            <div className="bg-gray-800/60 rounded-lg p-2">
              <div className="text-xs text-gray-500 mb-0.5">매수 필요</div>
              <div className={`text-sm font-semibold ${totalBuySummary > 0 ? PROFIT_COLOR : "text-gray-400"}`}>
                {totalBuySummary > 0 ? fmtKrw(totalBuySummary) : "—"}
              </div>
            </div>
            <div className="bg-gray-800/60 rounded-lg p-2">
              <div className="text-xs text-gray-500 mb-0.5">리밸런싱 후 예수금</div>
              <div className={`text-sm font-semibold ${cashAfterCls}`}>
                {cashAfter >= 0 ? "+" : ""}
                {fmtKrw(cashAfter)}
              </div>
            </div>
          </div>
          {cashAfter < 0 && (
            <div className="text-xs text-red-400 mt-2">
              예수금 부족 — 매도 후 매수하거나 수량을 조정하세요
            </div>
          )}
        </div>

        {/* 종목별 실제 거래 계획 패널 — 매도 먼저, 매수 나중 */}
        {(buyItems.length > 0 || sellItems.length > 0) && (
          <div className="rounded-xl bg-gray-800/60 border border-gray-700/50 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-xs font-medium text-gray-300">종목별 거래 계획</div>
              <button
                onClick={() => setShowTradePlan((v) => !v)}
                className="sm:hidden text-xs text-gray-500 hover:text-gray-300 transition-colors"
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
                          {Math.abs(Math.round(item.shares_to_trade!))}주 × {fmtKrw(item.current_price_krw!)}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className={`font-medium ${LOSS_COLOR}`}>{fmtKrw(calcTradeKrw(item))}</div>
                        <div className="text-gray-500 mt-0.5">수수료 {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}</div>
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
                          {Math.abs(Math.round(item.shares_to_trade!))}주 × {fmtKrw(item.current_price_krw!)}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className={`font-medium ${PROFIT_COLOR}`}>{fmtKrw(calcTradeKrw(item))}</div>
                        <div className="text-gray-500 mt-0.5">수수료 {fmtKrw(calcTradeKrw(item) * TRADING_FEE_RATE)}</div>
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
                {unpricedItems.map((i) => i.name).join(", ")} 등 {unpricedItems.length}개 종목은
                현재가 미조회로 거래 계획에서 제외됨
              </div>
            )}
          </div>
        )}
      </div>

      {/* 리밸런싱 비중 테이블 — 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-700">
        {analysis.items.map((item, idx) => (
          <RebalancingItemMobileCard key={idx} item={item} />
        ))}
      </div>

      {/* 리밸런싱 비중 테이블 — 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-xs text-gray-400">
              <th className="text-left py-2 px-3 font-medium sticky left-0 bg-gray-800 z-10">
                종목
              </th>
              <th className="text-right py-2 px-3 font-medium">현재 비중</th>
              <th className="text-left py-2 px-3 font-medium">목표 비중</th>
              <th className="text-right py-2 px-3 font-medium">차이</th>
              <th className="text-right py-2 px-3 font-medium">현재/목표</th>
              <th className="text-right py-2 px-3 font-medium">매수/매도</th>
              <th className="text-right py-2 px-3 font-medium">주수</th>
              <th className="text-right py-2 px-3 font-medium">10년 수익률</th>
            </tr>
          </thead>
          <tbody>
            {analysis.items.map((item, idx) => (
              <RebalancingItemRow key={idx} item={item} />
            ))}
          </tbody>
        </table>
      </div>

      {/* 상세 지표 (집중도 · CAGR) — 접기/펼치기 */}
      {(() => {
        const currentHHI = analysis.items.reduce((s, i) => s + i.current_weight_pct ** 2, 0);
        const targetHHI = analysis.items
          .filter((i) => i.target_weight_pct > 0)
          .reduce((s, i) => s + i.target_weight_pct ** 2, 0);

        function hhiLabel(hhi: number) {
          if (hhi < 1000) return { text: "분산형", cls: "text-green-400" };
          if (hhi < 2500) return { text: "보통", cls: "text-yellow-400" };
          return { text: "집중형", cls: "text-red-400" };
        }

        const curLabel = hhiLabel(currentHHI);
        const tgtLabel = hhiLabel(targetHHI);

        return (
          <div className="border border-gray-700/50 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowDetails((v) => !v)}
              className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-gray-400 hover:bg-gray-700/40 transition-colors"
            >
              <span className="font-medium">상세 지표</span>
              <span>{showDetails ? "▲" : "▼"}</span>
            </button>
            {showDetails && (
              <div className="px-4 pb-4 pt-2 space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div
                    className="bg-gray-700 rounded-xl p-3 text-center"
                    title="집중도 지수(HHI): 낮을수록 종목이 고르게 분산된 포트폴리오입니다"
                  >
                    <div className="text-xs text-gray-400 mb-1">현재 집중도</div>
                    <div className={`text-sm font-semibold ${curLabel.cls}`}>{curLabel.text}</div>
                    <div className="text-xs text-gray-500 mt-0.5">HHI {currentHHI.toFixed(0)}</div>
                  </div>
                  <div
                    className="bg-gray-700 rounded-xl p-3 text-center"
                    title="리밸런싱 후 목표 집중도"
                  >
                    <div className="text-xs text-gray-400 mb-1">목표 집중도</div>
                    <div className={`text-sm font-semibold ${tgtLabel.cls}`}>{tgtLabel.text}</div>
                    <div className="text-xs text-gray-500 mt-0.5">HHI {targetHHI.toFixed(0)}</div>
                  </div>
                </div>
                {hasCagrData && (
                  <div className="grid grid-cols-2 gap-3">
                    <CagrCard label="현재 포트폴리오 CAGR" cagr={analysis.current_weighted_cagr_10y_pct} />
                    <CagrCard label="목표 포트폴리오 CAGR" cagr={analysis.target_weighted_cagr_10y_pct} />
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* 배당 분석 섹션 */}
      {hasDividendData && <RebalancingDividendSection analysis={analysis} />}

      {/* 미추적 보유 종목 */}
      {(analysis.untracked_holdings ?? []).length > 0 && (
        <div className="bg-amber-900/20 border border-amber-700/30 rounded-xl p-4">
          <div className="text-xs font-medium text-amber-400 mb-2">
            포트폴리오 미포함 보유 종목 ({(analysis.untracked_holdings ?? []).length}개)
          </div>
          <div className="space-y-1.5">
            {(analysis.untracked_holdings ?? []).map((h, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs">
                <div className="min-w-0">
                  <span className="font-medium text-gray-200 truncate">{h.name}</span>
                  <span className="text-gray-500 ml-1.5">{h.ticker}</span>
                </div>
                <div className="text-right shrink-0 ml-3">
                  <span className="text-gray-300">{fmtKrw(h.current_value_krw)}</span>
                  <span className="text-gray-500 ml-1">({h.current_weight_pct.toFixed(1)}%)</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-xs text-gray-500 text-right">
        분석 시점:{" "}
        {new Date(analysis.analyzed_at).toLocaleTimeString("ko-KR", {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </div>

      {/* 모바일: 하단 고정 실행 버튼 */}
      <div className="sm:hidden fixed bottom-16 left-0 right-0 px-4 z-20 pb-2">
        <button
          onClick={() => setExecutionOpen(true)}
          disabled={kisAccounts.length === 0}
          className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-3 rounded-xl text-sm font-semibold shadow-lg disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
        >
          ⚡ 리밸런싱 실행
        </button>
      </div>

      {executionOpen && (
        <ErrorBoundary variant="section">
          <RebalancingExecutionModal
            portfolioId={portfolioId}
            analysis={analysis}
            accounts={accounts}
            onExecuted={onExecuted}
            onClose={() => setExecutionOpen(false)}
          />
        </ErrorBoundary>
      )}
    </div>
  );
}
