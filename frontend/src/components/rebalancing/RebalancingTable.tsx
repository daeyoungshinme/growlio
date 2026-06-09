import { useState } from "react";
import { ExecutionResult, RebalancingAnalysis, RebalancingItem } from "../../api/rebalancing";
import { AssetAccount } from "../../api/assets";
import { RebalancingAlert } from "../../api/alerts";
import { fmtKrw } from "../../utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "../../utils/colors";
import { Bell } from "lucide-react";
import { RebalancingExecutionModal } from "./RebalancingExecutionModal";
import ErrorBoundary from "../ErrorBoundary";
import {
  CagrCard,
  DiffCell,
  DividendDiffCell,
  Return10yCell,
  SharesCell,
  WeightBar,
  WeightDiffBadge,
} from "./RebalancingCells";

// ─── 테이블 행 컴포넌트 ────────────────────────────────────────────────────────

function RebalancingItemMobileCard({ item }: { item: RebalancingItem }) {
  const isUntracked = item.target_weight_pct === 0 && item.diff_krw < 0;
  return (
    <div className="py-3 px-1">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="font-medium text-gray-100 truncate text-sm">{item.name}</p>
            {isUntracked && <span className="text-xs text-amber-500 shrink-0">목표 외</span>}
          </div>
          <p className="text-xs text-gray-400">
            {item.ticker} · 현재 {item.current_weight_pct.toFixed(1)}%
          </p>
        </div>
        <div className="text-right shrink-0">
          <DiffCell diff={item.diff_krw} />
          <p className="text-xs text-gray-400 mt-0.5">
            <SharesCell item={item} />
          </p>
        </div>
      </div>
      <div className="mt-2">
        <WeightBar current={item.current_weight_pct} target={item.target_weight_pct} />
      </div>
      <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400 flex-wrap">
        <span>현재 {fmtKrw(item.current_value_krw)}</span>
        <span>→ 목표 {fmtKrw(item.target_value_krw)}</span>
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
        <DiffCell diff={item.diff_krw} />
      </td>
      <td className="py-3.5 px-3 text-right">
        <SharesCell item={item} />
      </td>
      <td className="py-3.5 px-3">
        <Return10yCell item={item} />
      </td>
    </tr>
  );
}

// ─── 배당 분석 섹션 ────────────────────────────────────────────────────────────

interface RebalancingDividendSectionProps {
  analysis: RebalancingAnalysis;
}

function RebalancingDividendSection({ analysis }: RebalancingDividendSectionProps) {
  const [showDividendDetail, setShowDividendDetail] = useState(false);

  const currentDiv = analysis.current_portfolio_annual_dividend ?? 0;
  const targetDiv = analysis.target_portfolio_annual_dividend ?? 0;
  const totalCurrentDiv = analysis.total_current_annual_dividend ?? currentDiv;
  const divDiff = targetDiv - totalCurrentDiv;
  const divDiffPct = totalCurrentDiv > 0 ? (divDiff / totalCurrentDiv) * 100 : 0;

  const dividendItems = analysis.items.filter(
    (i) => i.ticker !== "CASH" && (i.dividend_yield ?? 0) > 0
  );

  return (
    <div className="bg-gray-700/50 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-gray-200">배당 분석</div>
        {dividendItems.length > 0 && (
          <button
            onClick={() => setShowDividendDetail((v) => !v)}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            {showDividendDetail ? "▲ 접기" : "▼ 종목별 상세"}
          </button>
        )}
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">
            <span className="sm:hidden">현재 배당</span>
            <span className="hidden sm:inline">현재 연간 배당</span>
          </div>
          <div className="text-sm font-semibold text-gray-100">{fmtKrw(totalCurrentDiv)}</div>
          <div className="text-xs text-gray-500 mt-0.5 hidden sm:block">전체 보유 기준</div>
        </div>
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">
            <span className="sm:hidden">리밸 후 배당</span>
            <span className="hidden sm:inline">리밸런싱 후 연간 배당</span>
          </div>
          <div className="text-sm font-semibold text-gray-100">{fmtKrw(targetDiv)}</div>
        </div>
        <div
          className={`col-span-1 rounded-xl p-3 text-center ${
            divDiff >= 0 ? "bg-green-900/30" : "bg-red-900/30"
          }`}
        >
          <div className="text-xs text-gray-400 mb-1">배당 증감</div>
          <div
            className={`text-sm font-semibold ${divDiff >= 0 ? "text-green-400" : "text-red-400"}`}
          >
            {divDiff >= 0 ? "+" : ""}{fmtKrw(divDiff)}
          </div>
          {totalCurrentDiv > 0 && (
            <div className={`text-xs ${divDiff >= 0 ? "text-green-500" : "text-red-500"}`}>
              ({divDiff >= 0 ? "+" : ""}{divDiffPct.toFixed(1)}%)
            </div>
          )}
        </div>
      </div>

      {/* 종목별 배당 상세 */}
      {showDividendDetail && dividendItems.length > 0 && (
        <>
          {/* 모바일 카드 */}
          <div className="sm:hidden divide-y divide-gray-700 mt-2">
            {dividendItems.map((item, idx) => (
              <div key={idx} className="py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-gray-100 text-xs truncate">{item.name}</p>
                    <p className="text-xs text-gray-400">
                      {item.ticker}
                      {item.dividend_yield != null &&
                        ` · 배당율 ${item.dividend_yield.toFixed(2)}%`}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <DividendDiffCell diff={item.annual_dividend_diff_krw ?? 0} />
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-gray-400 overflow-hidden">
                  <span className="truncate">현재 {fmtKrw(item.annual_dividend_current_krw ?? 0)}</span>
                  <span className="shrink-0">→</span>
                  <span className="truncate">목표 {fmtKrw(item.annual_dividend_target_krw ?? 0)}</span>
                </div>
              </div>
            ))}
          </div>

          {/* 데스크탑 테이블 */}
          <div className="hidden sm:block overflow-x-auto mt-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-600 text-xs text-gray-400">
                  <th className="text-left py-2 px-3 font-medium">종목</th>
                  <th className="text-right py-2 px-3 font-medium">배당수익률</th>
                  <th className="text-right py-2 px-3 font-medium">현재 연배당</th>
                  <th className="text-right py-2 px-3 font-medium">목표 연배당</th>
                  <th className="text-right py-2 px-3 font-medium">배당 증감</th>
                </tr>
              </thead>
              <tbody>
                {dividendItems.map((item, idx) => (
                  <tr key={idx} className="border-b border-gray-700 hover:bg-gray-700">
                    <td className="py-2 px-3">
                      <div className="font-medium text-gray-100 text-xs truncate max-w-[120px]">
                        {item.name}
                      </div>
                      <div className="text-xs text-gray-400">{item.ticker}</div>
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {item.dividend_yield != null ? `${item.dividend_yield.toFixed(2)}%` : "-"}
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {fmtKrw(item.annual_dividend_current_krw ?? 0)}
                    </td>
                    <td className="py-2 px-3 text-right text-xs text-gray-300">
                      {fmtKrw(item.annual_dividend_target_krw ?? 0)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <DividendDiffCell diff={item.annual_dividend_diff_krw ?? 0} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ─── 메인 컴포넌트 ──────────────────────────────────────────────────────────────

interface Props {
  analysis: RebalancingAnalysis;
  portfolioId: string;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
  existingAlert?: RebalancingAlert;
  onAlertClick?: () => void;
}

export default function RebalancingTable({
  analysis,
  portfolioId,
  accounts,
  onExecuted,
  existingAlert,
  onAlertClick,
}: Props) {
  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS");
  const [executionOpen, setExecutionOpen] = useState(false);

  const hasDividendData =
    (analysis.target_portfolio_annual_dividend ?? 0) > 0 ||
    (analysis.total_current_annual_dividend ?? analysis.current_portfolio_annual_dividend ?? 0) > 0;
  const hasCagrData =
    analysis.target_weighted_cagr_10y_pct != null ||
    analysis.current_weighted_cagr_10y_pct != null;

  return (
    <div className="space-y-4">
      {/* 실행 버튼 행 */}
      <div className="flex items-center gap-2">
        {/* 모바일 전용: 알림설정 버튼 */}
        <div className="sm:hidden flex items-center gap-1.5">
          {existingAlert && (
            <span
              className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                existingAlert.mode === "AUTO"
                  ? "bg-orange-100 dark:bg-orange-950 text-orange-700 dark:text-orange-400"
                  : "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400"
              }`}
            >
              {existingAlert.mode === "AUTO" ? "자동" : "알림"}
            </span>
          )}
          {onAlertClick && (
            <button
              onClick={onAlertClick}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border transition-colors ${
                existingAlert
                  ? "border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950"
                  : "border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
            >
              <Bell size={11} />
              {existingAlert ? "설정 변경" : "알림설정"}
            </button>
          )}
        </div>

        {/* 리밸런싱 실행 버튼 (우측 정렬) */}
        <div className="flex items-center gap-2 ml-auto">
          {kisAccounts.length === 0 && (
            <span className="text-xs text-gray-500 hidden sm:inline">
              KIS 증권계좌 연동 시 자동 주문 가능
            </span>
          )}
          <button
            onClick={() => setExecutionOpen(true)}
            disabled={kisAccounts.length === 0}
            className="bg-indigo-600 text-white px-4 py-1.5 text-xs rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            title={kisAccounts.length === 0 ? "자산관리에서 KIS 증권계좌를 연동하세요" : ""}
          >
            ⚡ 리밸런싱 실행
          </button>
        </div>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gray-700 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">
            {analysis.base_type === "STOCK_ONLY" ? "기준 자산(주식)" : "기준 자산(전체)"}
          </div>
          <div className="text-sm font-semibold text-gray-100">
            {fmtKrw(analysis.base_value_krw)}
          </div>
        </div>
        <div className="bg-red-900/30 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">총 매수 필요</div>
          <div className={`text-sm font-semibold ${PROFIT_COLOR}`}>
            {fmtKrw(
              analysis.items.filter((i) => i.diff_krw > 0).reduce((s, i) => s + i.diff_krw, 0)
            )}
          </div>
        </div>
        <div className="bg-blue-900/30 rounded-xl p-3 text-center">
          <div className="text-xs text-gray-400 mb-1">총 매도 필요</div>
          <div className={`text-sm font-semibold ${LOSS_COLOR}`}>
            {fmtKrw(
              Math.abs(
                analysis.items.filter((i) => i.diff_krw < 0).reduce((s, i) => s + i.diff_krw, 0)
              )
            )}
          </div>
        </div>
      </div>

      {/* 집중도 지표 (HHI) + 거래 비용 */}
      {(() => {
        const TRADING_FEE_RATE = 0.00014;
        const currentHHI = analysis.items.reduce(
          (s, i) => s + i.current_weight_pct ** 2,
          0
        );
        const targetHHI = analysis.items
          .filter((i) => i.target_weight_pct > 0)
          .reduce((s, i) => s + i.target_weight_pct ** 2, 0);

        function hhiLabel(hhi: number) {
          if (hhi < 1000) return { text: "분산형", cls: "text-green-400" };
          if (hhi < 2500) return { text: "보통", cls: "text-yellow-400" };
          return { text: "집중형", cls: "text-red-400" };
        }

        const totalBuy = analysis.items
          .filter((i) => i.diff_krw > 0)
          .reduce((s, i) => s + i.diff_krw, 0);
        const totalSell = Math.abs(
          analysis.items.filter((i) => i.diff_krw < 0).reduce((s, i) => s + i.diff_krw, 0)
        );
        const estFee = (totalBuy + totalSell) * TRADING_FEE_RATE;
        const curLabel = hhiLabel(currentHHI);
        const tgtLabel = hhiLabel(targetHHI);

        return (
          <div className="space-y-2">
            <div className="grid grid-cols-2 gap-3">
              <div
                className="bg-gray-700 rounded-xl p-3 text-center"
                title="HHI (허핀달-허쉬만 지수): 포트폴리오 집중도. 낮을수록 분산"
              >
                <div className="text-xs text-gray-400 mb-1">현재 집중도 (HHI)</div>
                <div className={`text-sm font-semibold ${curLabel.cls}`}>
                  {currentHHI.toFixed(0)}
                </div>
                <div className={`text-xs mt-0.5 ${curLabel.cls}`}>{curLabel.text}</div>
              </div>
              <div
                className="bg-gray-700 rounded-xl p-3 text-center"
                title="리밸런싱 후 목표 HHI"
              >
                <div className="text-xs text-gray-400 mb-1">목표 집중도 (HHI)</div>
                <div className={`text-sm font-semibold ${tgtLabel.cls}`}>
                  {targetHHI.toFixed(0)}
                </div>
                <div className={`text-xs mt-0.5 ${tgtLabel.cls}`}>{tgtLabel.text}</div>
              </div>
            </div>
            {estFee > 0 && (
              <div className="bg-gray-700/50 rounded-xl px-4 py-2.5 flex items-center justify-between text-xs">
                <span className="text-gray-400">
                  예상 거래 비용{" "}
                  <span className="text-gray-500">(수수료 0.014%)</span>
                </span>
                <span className="text-gray-200 font-medium">{fmtKrw(estFee)}</span>
              </div>
            )}
          </div>
        );
      })()}

      {/* 포트폴리오 10년 수익률 요약 */}
      {hasCagrData && (
        <div className="grid grid-cols-2 gap-3">
          <CagrCard label="현재 포트폴리오 CAGR" cagr={analysis.current_weighted_cagr_10y_pct} />
          <CagrCard label="목표 포트폴리오 CAGR" cagr={analysis.target_weighted_cagr_10y_pct} />
        </div>
      )}

      {/* 리밸런싱 테이블 — 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-700">
        {analysis.items.map((item, idx) => (
          <RebalancingItemMobileCard key={idx} item={item} />
        ))}
      </div>

      {/* 리밸런싱 테이블 — 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 text-xs text-gray-400">
              <th className="text-left py-2 px-3 font-medium sticky left-0 bg-gray-800 z-10">종목</th>
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
