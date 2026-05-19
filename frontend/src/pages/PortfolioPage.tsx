import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, Treemap, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { syncAccount } from "../api/assets";
import PortfolioAnalysisTab from "../components/portfolio-analysis/PortfolioAnalysisTab";
import AccountCard from "../components/assets/AccountCard";
import StockHoldingsTable from "../components/assets/StockHoldingsTable";
import { useThemeStore } from "../stores/themeStore";
import { fmtKrw, fmtKrwShort } from "../utils/format";
import { PIE_COLORS } from "../utils/colors";
import type { PortfolioOverview, DividendByTicker, DividendYield } from "../types";

interface DividendSummary {
  annual_received: number;
  estimated_annual: number;
  monthly_breakdown: { month: string; amount: number }[];
  monthly_ticker_breakdown: { month: string; ticker: string | null; amount: number }[];
}

const fetchOverview = () => api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);

// ── 서브 컴포넌트 ──────────────────────────────────────

function StatCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string;
  color?: "red" | "blue" | "green" | "gray";
}) {
  const textColor = {
    red: "text-red-500", green: "text-green-600",
    blue: "text-blue-600", gray: "text-gray-900 dark:text-gray-50",
  }[color ?? "gray"];
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${textColor}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

function TreemapCell(props: Record<string, unknown>) {
  const x = (props.x as number) ?? 0;
  const y = (props.y as number) ?? 0;
  const width = (props.width as number) ?? 0;
  const height = (props.height as number) ?? 0;
  const name = (props.name as string) ?? "";
  const pct = (props.pct as number) ?? 0;
  const ticker = (props.ticker as string) ?? "";
  const index = (props.index as number) ?? 0;
  const color = PIE_COLORS[index % PIE_COLORS.length];

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} stroke="#fff" strokeWidth={2} rx={3} />
      {width > 50 && height > 30 && (
        <>
          <text x={x + width / 2} y={y + height / 2 - 7} fill="#fff"
            textAnchor="middle" fontSize={11} fontWeight="bold">
            {name.length > 8 ? name.slice(0, 7) + "…" : name}
          </text>
          <text x={x + width / 2} y={y + height / 2 + 9} fill="rgba(255,255,255,0.85)"
            textAnchor="middle" fontSize={10}>
            {pct.toFixed(1)}%
          </text>
          {height > 55 && ticker && (
            <text x={x + width / 2} y={y + height / 2 + 22} fill="rgba(255,255,255,0.6)"
              textAnchor="middle" fontSize={9}>
              {ticker}
            </text>
          )}
        </>
      )}
    </g>
  );
}

function TreemapChart({ data, title }: { data: { name: string; ticker?: string; value: number; pct: number }[]; title: string }) {
  const isDark = useThemeStore((s) => s.isDark);
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{title}</h3>
      {data.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-gray-300 dark:text-gray-600 text-sm">데이터 없음</div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <Treemap data={data} dataKey="value" content={<TreemapCell />}>
            <Tooltip
              formatter={(value: number, _name: string, props) => [
                `${fmtKrwShort(value)}원 (${(props.payload?.pct ?? 0).toFixed(1)}%)`,
                props.payload?.ticker
                  ? `${props.payload.name} (${props.payload.ticker})`
                  : props.payload?.name,
              ]}
              contentStyle={{
                backgroundColor: isDark ? "#1f2937" : "#ffffff",
                border: `1px solid ${isDark ? "#374151" : "#e5e7eb"}`,
                color: isDark ? "#f9fafb" : "#111827",
                fontSize: 12,
              }}
              labelStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
              itemStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
            />
          </Treemap>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ── 메인 페이지 ────────────────────────────────────────
const TABS = ["증권사 계좌", "종목 현황", "배당 현황", "포트폴리오 분석"] as const;
type Tab = typeof TABS[number];

const DIV_SUBTABS = ["종목별 배당", "월별 배당"] as const;
type DivSubTab = typeof DIV_SUBTABS[number];

const MONTH_LABELS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

export default function PortfolioPage() {
  const isDark = useThemeStore((s) => s.isDark);
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("증권사 계좌");
  const [divSubTab, setDivSubTab] = useState<DivSubTab>("종목별 배당");
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [syncingAll, setSyncingAll] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["portfolio-overview"],
    queryFn: fetchOverview,
    refetchInterval: 60_000,
  });

  const { data: dividendData = [], isLoading: divLoading, isError: divError } = useQuery({
    queryKey: ["dividend-positions"],
    queryFn: () => api.get<DividendYield[]>("/dividends/positions").then((r) => r.data),
    enabled: tab === "종목 현황" || tab === "배당 현황",
    staleTime: 1000 * 60 * 60,
  });

  const { data: divSummary } = useQuery({
    queryKey: ["dividend-summary"],
    queryFn: () => api.get<DividendSummary>("/dividends/summary").then((r) => r.data),
    enabled: tab === "배당 현황",
    staleTime: 1000 * 60 * 60,
  });

  const { data: dividendByTicker = [] } = useQuery({
    queryKey: ["dividend-by-ticker"],
    queryFn: () => api.get<DividendByTicker[]>("/dividends/by-ticker").then((r) => r.data),
    enabled: tab === "배당 현황",
    staleTime: 1000 * 60 * 60,
  });

  const handleSync = async (id: string) => {
    setSyncingId(id);
    setSyncError(null);
    try {
      await syncAccount(id);
      qc.invalidateQueries({ queryKey: ["portfolio-overview"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["dividend-by-ticker"] });
      qc.invalidateQueries({ queryKey: ["dividend-summary"] });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "동기화에 실패했습니다";
      setSyncError(msg);
    } finally {
      setSyncingId(null);
    }
  };

  const handleSyncAll = async () => {
    if (!data) return;
    const accounts = data.accounts.filter(
      (a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER"
    );
    setSyncingAll(true);
    setSyncError(null);
    try {
      for (const acc of accounts) {
        setSyncingId(acc.id);
        await syncAccount(acc.id);
      }
      qc.invalidateQueries({ queryKey: ["portfolio-overview"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["dividend-by-ticker"] });
      qc.invalidateQueries({ queryKey: ["dividend-summary"] });
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "일부 계좌 동기화에 실패했습니다";
      setSyncError(msg);
    } finally {
      setSyncingAll(false);
      setSyncingId(null);
    }
  };

  if (isLoading) return <div className="flex items-center justify-center h-64 text-gray-400">로딩 중...</div>;
  if (error || !data) return <div className="text-red-500 p-4">데이터를 불러오지 못했습니다</div>;

  const stockAccounts = data.accounts.filter((a) => a.asset_type.startsWith("STOCK") || a.asset_type === "CASH_OTHER");

  const DOMESTIC_MARKETS = ["KOSPI", "KOSDAQ", "KRX"];
  const marketChartData = (() => {
    let domestic = 0;
    let foreign = 0;
    for (const p of data.all_positions) {
      if (DOMESTIC_MARKETS.includes(p.market)) domestic += p.value_krw;
      else foreign += p.value_krw;
    }
    const total = domestic + foreign;
    if (total === 0) return [];
    const items = [];
    if (domestic > 0) items.push({ name: "국내 주식", value: domestic, pct: (domestic / total) * 100 });
    if (foreign > 0) items.push({ name: "해외 주식", value: foreign, pct: (foreign / total) * 100 });
    return items;
  })();

  const stockChartData = data.stock_allocation.map((a) => ({
    name: a.name,
    ticker: a.ticker,
    value: a.value_krw ?? 0,
    pct: a.pct,
  }));

  const pnlColor = data.unrealized_pnl_krw >= 0 ? "red" : "blue" as const;
  const retColor = data.stock_return_pct >= 0 ? "red" : "blue" as const;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">포트폴리오</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSyncAll}
            disabled={syncingAll || !!syncingId}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
          >
            <RefreshCw size={14} className={syncingAll ? "animate-spin" : ""} />
            {syncingAll ? "갱신 중..." : "전체 갱신"}
          </button>
          <span className="text-xs text-gray-400 dark:text-gray-500">{stockAccounts.length}개 증권사 계좌</span>
        </div>
      </div>

      {/* 상단 요약 */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="주식 총평가액" value={`${fmtKrwShort(Math.round(data.total_invested_krw / 1e6) * 1e6 + Math.round(data.unrealized_pnl_krw / 1e6) * 1e6)}원`} color="blue" />
        <StatCard label="총 매입금액" value={`${fmtKrwShort(data.total_invested_krw)}원`} color="gray" />
        <StatCard label="평가손익"
          value={`${data.unrealized_pnl_krw >= 0 ? "+" : ""}${fmtKrwShort(data.unrealized_pnl_krw)}원`}
          color={pnlColor} />
        <StatCard label="주식 수익률"
          value={`${data.stock_return_pct >= 0 ? "+" : ""}${data.stock_return_pct.toFixed(2)}%`}
          color={retColor} />
      </div>

      {/* 탭 */}
      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 w-fit">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            }`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "증권사 계좌" && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <TreemapChart data={marketChartData} title="국내/해외 주식 비중" />
            <TreemapChart data={stockChartData} title="종목별 비중 (주식 내)" />
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-700 dark:text-gray-300">증권사 계좌</h2>
              <p className="text-xs text-gray-400 dark:text-gray-500">계좌 추가·관리는 <strong>자산관리</strong> 메뉴에서</p>
            </div>

            {syncError && (
              <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 text-sm rounded-lg px-4 py-2.5">
                {syncError}
              </div>
            )}

            {stockAccounts.length === 0 ? (
              <div className="bg-gray-50 dark:bg-gray-900 rounded-2xl border border-dashed border-gray-300 dark:border-gray-700 p-10 text-center text-gray-400 dark:text-gray-500 text-sm">
                등록된 증권사 계좌가 없습니다. <strong>자산관리</strong> 메뉴에서 계좌를 추가하세요.
              </div>
            ) : (
              stockAccounts.map((acc) => (
                <AccountCard
                  key={acc.id}
                  acc={acc}
                  syncing={syncingId === acc.id || syncingAll}
                  onSync={() => handleSync(acc.id)}
                />
              ))
            )}
          </div>
        </>
      )}

      {tab === "종목 현황" && (
        <>
          <TreemapChart data={stockChartData} title="종목별 비중" />
          {(() => {
            const dividendMap = Object.fromEntries(
              dividendData.map((d) => [`${d.ticker}-${d.market}`, d])
            );
            return (
              <StockHoldingsTable
                positions={data.all_positions}
                totalStock={data.total_stock_krw}
                dividendMap={dividendMap}
                divLoading={divLoading}
                divError={divError}
              />
            );
          })()}
        </>
      )}

      {tab === "배당 현황" && (() => {
        const now = new Date();
        const currentYear = now.getFullYear();
        const currentMonth = now.getMonth() + 1;

        const positionsDivMap = Object.fromEntries(
          dividendData.map((d) => [`${d.ticker}-${d.market}`, d])
        );
        const tickerOnlyDivMap: Record<string, DividendYield> = {};
        for (const d of dividendData) {
          const existing = tickerOnlyDivMap[d.ticker];
          if (!existing || d.investment_yield > existing.investment_yield) {
            tickerOnlyDivMap[d.ticker] = d;
          }
        }
        const positionsQtyMap: Record<string, number> = {};
        const tickerOnlyQtyMap: Record<string, number> = {};
        for (const p of data.all_positions) {
          const key = `${p.ticker}-${p.market}`;
          positionsQtyMap[key] = (positionsQtyMap[key] ?? 0) + p.qty;
          tickerOnlyQtyMap[p.ticker] = (tickerOnlyQtyMap[p.ticker] ?? 0) + p.qty;
        }

        const totalEstimated = dividendByTicker.reduce((s, d) => s + d.estimated_annual_krw, 0);
        const dividendChartData = dividendByTicker
          .filter((d) => d.estimated_annual_krw > 0)
          .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw)
          .map((d) => ({
            name: d.name,
            ticker: d.ticker ?? undefined,
            value: d.estimated_annual_krw,
            pct: totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0,
          }));

        const estimatedMonthly = dividendByTicker.reduce((s, d) => s + d.estimated_monthly_krw, 0);
        const monthlyEstimateByMonth = Array.from({ length: 12 }, (_, i) => {
          const m = i + 1;
          return dividendByTicker.reduce((sum, d) => {
            if (d.dividend_months.length === 0) {
              return sum + d.estimated_monthly_krw;
            }
            if (d.dividend_months.includes(m)) {
              return sum + Math.round(d.estimated_annual_krw / d.dividend_months.length);
            }
            return sum;
          }, 0);
        });
        const monthCells = Array.from({ length: 12 }, (_, i) => {
          const m = i + 1;
          const monthStr = `${currentYear}-${String(m).padStart(2, "0")}`;
          const actual = divSummary?.monthly_breakdown.find((x) => x.month === monthStr);
          const isPast = m < currentMonth;
          return { month: m, actual: actual?.amount ?? null, estimated: monthlyEstimateByMonth[i], isPast };
        });

        const estAnnual = totalEstimated;
        const received = divSummary?.annual_received ?? 0;

        // 월별 배당 서브탭용 BarChart 데이터
        const barData = monthCells.map((cell) => ({
          name: MONTH_LABELS[cell.month - 1],
          month: cell.month,
          actual: cell.actual && cell.actual > 0 ? cell.actual : 0,
          estimated: (!cell.actual || cell.actual === 0) && !cell.isPast ? cell.estimated : 0,
        }));

        // 선택 월 배당 종목
        const selectedMonthTickers = dividendByTicker.filter((d) =>
          d.dividend_months.includes(selectedMonth)
        );
        const monthStr = `${currentYear}-${String(selectedMonth).padStart(2, "0")}`;
        const selectedMonthActual = divSummary?.monthly_breakdown.find(
          (x) => x.month === monthStr
        );
        const monthTickerActualMap: Record<string, number> = {};
        for (const entry of (divSummary?.monthly_ticker_breakdown ?? [])) {
          const key = `${entry.month}-${entry.ticker ?? ""}`;
          monthTickerActualMap[key] = (monthTickerActualMap[key] ?? 0) + entry.amount;
        }

        return (
          <div className="space-y-6">
            {/* 요약 카드 */}
            <div className="grid grid-cols-3 gap-4">
              <StatCard
                label="예상 연간 배당금"
                value={estAnnual > 0 ? `${fmtKrwShort(estAnnual)}원` : "—"}
                sub="보유 종목 배당수익률 기준 추정"
                color="green"
              />
              <StatCard
                label="올해 수령 배당금"
                value={received > 0 ? `${fmtKrwShort(received)}원` : "—"}
                sub={received > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
                color="gray"
              />
              <StatCard
                label="월평균 예상 배당금"
                value={estimatedMonthly > 0 ? `${fmtKrwShort(estimatedMonthly)}원` : "—"}
                sub="연간 예상 배당금 ÷ 12"
                color="blue"
              />
            </div>

            {/* 서브탭 */}
            <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 w-fit">
              {DIV_SUBTABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setDivSubTab(t)}
                  className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    divSubTab === t ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {/* 서브탭: 종목별 배당 */}
            {divSubTab === "종목별 배당" && dividendChartData.length > 0 && (
              <div className="space-y-4">
                <TreemapChart data={dividendChartData} title="종목별 배당 비중 (예상 연간 기준)" />
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
                    <h3 className="font-semibold text-gray-800 dark:text-gray-200">종목별 배당 내역</h3>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                          <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
                          <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">투자배당율</th>
                          <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월</th>
                          <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">예상 연간 배당금</th>
                          <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">비중</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dividendByTicker
                          .filter((d) => d.estimated_annual_krw > 0)
                          .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw)
                          .map((d) => {
                            const pct = totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0;
                            const rowKey = `${d.ticker}-${d.market}`;
                            const posDiv = positionsDivMap[rowKey] ?? tickerOnlyDivMap[d.ticker ?? ""];
                            const posYield = posDiv?.investment_yield ?? 0;
                            const investmentYield = posYield > 0 ? posYield : (d.investment_yield ?? 0);
                            return (
                              <tr key={`${d.ticker}-${d.market}`} className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                                <td className="py-2 px-5">
                                  <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                                  <p className="text-[10px] text-gray-400 dark:text-gray-500">{d.ticker} · {d.market}</p>
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {divLoading ? (
                                    <span className="text-gray-300 dark:text-gray-600 text-xs">...</span>
                                  ) : investmentYield > 0 ? (
                                    <span className="font-medium text-green-600 dark:text-green-400">{investmentYield.toFixed(2)}%</span>
                                  ) : (
                                    <span className="text-gray-300 dark:text-gray-600">—</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {d.dividend_months.length === 0 ? (
                                    <span className="text-gray-300 dark:text-gray-600">—</span>
                                  ) : d.dividend_months.length === 12 ? (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-medium">
                                      월배당
                                    </span>
                                  ) : (
                                    <div className="flex flex-wrap gap-0.5 justify-end">
                                      {d.dividend_months.map((m) => (
                                        <span
                                          key={m}
                                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                                            d.dividend_months_is_manual
                                              ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                          }`}
                                        >
                                          {m}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right font-semibold text-gray-900 dark:text-gray-50">
                                  {fmtKrwShort(d.estimated_annual_krw)}원
                                </td>
                                <td className="py-2 px-5 text-right">
                                  <div className="flex items-center justify-end gap-1.5">
                                    <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                                      <div className="bg-green-500 h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
                                    </div>
                                    <span className="text-xs text-gray-500 dark:text-gray-400 w-10 text-right">{pct.toFixed(1)}%</span>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                      </tbody>
                      <tfoot>
                        <tr className="bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 font-semibold text-sm">
                          <td className="py-2.5 px-5 text-gray-500 dark:text-gray-400">합계</td>
                          <td className="py-2.5 px-3" />
                          <td className="py-2.5 px-3" />
                          <td className="py-2.5 px-3 text-right text-gray-900 dark:text-gray-50">{fmtKrwShort(totalEstimated)}원</td>
                          <td className="py-2.5 px-5 text-right text-gray-500 dark:text-gray-400">100%</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </div>
              </div>
            )}
            {divSubTab === "종목별 배당" && dividendChartData.length === 0 && (
              <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-10">배당 데이터가 없습니다.</p>
            )}

            {/* 서브탭: 월별 배당 */}
            {divSubTab === "월별 배당" && (
              <div className="space-y-4">
                {/* 12개월 BarChart */}
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
                  <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 배당 현황 ({currentYear})</h3>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart
                      data={barData}
                      margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                      onClick={(e) => {
                        if (e?.activePayload?.[0]) {
                          const d = e.activePayload[0].payload as { month: number };
                          setSelectedMonth(d.month);
                        }
                      }}
                    >
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 11, fill: "#9CA3AF" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tickFormatter={(v: number) =>
                          v >= 1e8 ? `${(v / 1e8).toFixed(1)}억` : v >= 1e4 ? `${Math.round(v / 1e4)}만` : `${v}`
                        }
                        tick={{ fontSize: 11, fill: "#9CA3AF" }}
                        axisLine={false}
                        tickLine={false}
                        width={48}
                      />
                      <Tooltip
                        formatter={(value: number, name: string) => [
                          `${fmtKrwShort(value)}원`,
                          name === "actual" ? "실수령" : "예상",
                        ]}
                        labelStyle={{ fontSize: 12, fontWeight: 600, color: isDark ? "#f9fafb" : "#111827" }}
                        itemStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
                        cursor={{ fill: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}
                        contentStyle={{
                          borderRadius: 8,
                          border: `1px solid ${isDark ? "#374151" : "#E5E7EB"}`,
                          fontSize: 12,
                          backgroundColor: isDark ? "#1f2937" : "#ffffff",
                          color: isDark ? "#f9fafb" : "#111827",
                        }}
                      />
                      <Bar dataKey="actual" stackId="a" radius={[0, 0, 0, 0]} cursor="pointer">
                        {barData.map((entry) => (
                          <Cell
                            key={entry.month}
                            fill={entry.month === selectedMonth ? "#15803D" : "#16A34A"}
                            opacity={entry.month === selectedMonth ? 1 : 0.75}
                          />
                        ))}
                      </Bar>
                      <Bar dataKey="estimated" stackId="a" radius={[4, 4, 0, 0]} cursor="pointer">
                        {barData.map((entry) => (
                          <Cell
                            key={entry.month}
                            fill={entry.month === selectedMonth ? "#4ADE80" : "#86EFAC"}
                            opacity={entry.month === selectedMonth ? 1 : 0.75}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                  <p className="text-[10px] text-gray-300 dark:text-gray-600 mt-2 text-right">
                    진한 초록: 실수령 · 연한 초록: 예상 | 막대 클릭 시 해당 월 상세 표시
                  </p>
                </div>

                {/* 선택 월 배당 내역 */}
                <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <h3 className="font-semibold text-gray-800 dark:text-gray-200">
                      {MONTH_LABELS[selectedMonth - 1]} 배당 종목
                      {selectedMonthActual && selectedMonthActual.amount > 0 ? (
                        <span className="ml-2 text-xs font-normal text-green-600 dark:text-green-400">
                          실수령 {fmtKrwShort(selectedMonthActual.amount)}원
                        </span>
                      ) : monthlyEstimateByMonth[selectedMonth - 1] > 0 ? (
                        <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
                          예상 {fmtKrwShort(monthlyEstimateByMonth[selectedMonth - 1])}원
                        </span>
                      ) : null}
                    </h3>
                    <span className="text-xs text-gray-400 dark:text-gray-500">{selectedMonthTickers.length}개 종목</span>
                  </div>
                  {selectedMonthTickers.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                            <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
                            <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">투자배당수익율</th>
                            <th className="py-2 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당금</th>
                            <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월 설정</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedMonthTickers
                            .sort((a, b) => {
                              const aCount = a.dividend_months.length > 0 ? a.dividend_months.length : 12;
                              const bCount = b.dividend_months.length > 0 ? b.dividend_months.length : 12;
                              return Math.round(b.estimated_annual_krw / bCount) - Math.round(a.estimated_annual_krw / aCount);
                            })
                            .map((d) => {
                              const payCount = d.dividend_months.length > 0 ? d.dividend_months.length : 12;
                              const payAmt = Math.round(d.estimated_annual_krw / payCount);
                              const usdPerPayment = d.estimated_monthly_usd != null
                                ? d.estimated_monthly_usd * 12 / payCount
                                : null;
                              const actualAmt = monthTickerActualMap[`${monthStr}-${d.ticker ?? ""}`];
                              return (
                              <tr key={`${d.ticker}-${d.market}`} className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                                <td className="py-2 px-5">
                                  <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                                  <p className="text-[10px] text-gray-400 dark:text-gray-500">{d.ticker} · {d.market}</p>
                                </td>
                                <td className="py-2 px-3 text-right font-medium text-green-600 dark:text-green-400">
                                  {d.investment_yield > 0 ? `${d.investment_yield.toFixed(2)}%` : "—"}
                                </td>
                                <td className="py-2 px-4 text-right">
                                  {actualAmt && actualAmt > 0 ? (
                                    <span className="font-medium text-green-600 dark:text-green-400">
                                      수령 {fmtKrw(actualAmt)}
                                    </span>
                                  ) : d.currency === "USD" && usdPerPayment != null && usdPerPayment > 0 ? (
                                    <span className="text-gray-500 dark:text-gray-400">
                                      {fmtKrw(payAmt)}(${usdPerPayment.toFixed(2)})
                                    </span>
                                  ) : payAmt > 0 ? (
                                    <span className="text-gray-500 dark:text-gray-400">
                                      예상 {fmtKrw(payAmt)}
                                    </span>
                                  ) : (
                                    <span className="text-gray-300 dark:text-gray-600">—</span>
                                  )}
                                </td>
                                <td className="py-2 px-5 text-right">
                                  <span
                                    className={`text-[10px] px-2 py-0.5 rounded-full ${
                                      d.dividend_months_is_manual
                                        ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                        : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                    }`}
                                  >
                                    {d.dividend_months_is_manual ? "수동" : "자동"}
                                  </span>
                                </td>
                              </tr>
                            );
                            })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-8">이 달에 배당 예정 종목이 없습니다.</p>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {tab === "포트폴리오 분석" && <PortfolioAnalysisTab />}
    </div>
  );
}
