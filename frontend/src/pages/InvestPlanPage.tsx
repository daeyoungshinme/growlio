import { useState, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { AlertTriangle, ChevronDown, ChevronUp, Settings2 } from "lucide-react";
import { api } from "../api/client";
import { fetchSettings } from "../api/settings";
import { fetchDCAAnalysis } from "../api/invest";
import { fetchTaxSummary, fetchOverseasPositionsTax } from "../api/tax";
import DCAProjectionChart from "../components/invest/DCAProjectionChart";
import TaxPlannerSection from "../components/invest/TaxPlannerSection";
import GoalTimelineCard from "../components/invest/GoalTimelineCard";
import MonthlyAchievementTable from "../components/invest/MonthlyAchievementTable";
import YearlyAchievementTable from "../components/invest/YearlyAchievementTable";
import { fmtKrw } from "../utils/format";
import { toast } from "../utils/toast";
import { STALE_TIME } from "../constants/queryConfig";
import { QUERY_KEYS } from "../constants/queryKeys";
import { invalidateDcaData } from "../utils/queryInvalidation";

interface GoalForm {
  monthly_deposit_amount: string;
  goal_annual_return_pct: string;
  goal_amount: string;
  goal_start_date: string;
  goal_initial_amount: string;
  annual_deposit_goal: string;
  retirement_target_year: string;
}

export default function InvestPlanPage() {
  const queryClient = useQueryClient();
  const location = useLocation();
  const currentYear = new Date().getFullYear();

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.dcaAnalysis,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.MEDIUM,
  });

  const [taxYear, setTaxYear] = useState(currentYear);
  const [showTax, setShowTax] = useState(false);
  const { data: taxData, isLoading: taxLoading } = useQuery({
    queryKey: QUERY_KEYS.taxSummary(taxYear),
    queryFn: () => fetchTaxSummary(taxYear),
    staleTime: STALE_TIME.LONG,
    enabled: showTax,
  });
  const { data: positionsData, isLoading: posLoading } = useQuery({
    queryKey: QUERY_KEYS.overseasPositionsTax,
    queryFn: fetchOverseasPositionsTax,
    staleTime: STALE_TIME.MEDIUM,
    enabled: showTax,
  });

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autoOpenTriggered, setAutoOpenTriggered] = useState(false);
  const [form, setForm] = useState<GoalForm>({
    monthly_deposit_amount: "",
    goal_annual_return_pct: "",
    goal_amount: "",
    goal_start_date: "",
    goal_initial_amount: "",
    annual_deposit_goal: "",
    retirement_target_year: "",
  });

  const openEdit = async () => {
    const s = data?.settings;
    let annual_deposit_goal = "";
    let retirement_target_year = "";
    if (data) {
      const settingsData = await fetchSettings();
      annual_deposit_goal = settingsData.annual_deposit_goal ? String(settingsData.annual_deposit_goal) : "";
      retirement_target_year = settingsData.retirement_target_year ? String(settingsData.retirement_target_year) : "";
    }
    setForm({
      monthly_deposit_amount: s?.monthly_deposit_amount ? String(s.monthly_deposit_amount) : "",
      goal_annual_return_pct: s?.goal_annual_return_pct ? String(s.goal_annual_return_pct) : "",
      goal_amount: s?.goal_amount ? String(s.goal_amount) : "",
      goal_start_date: s?.goal_start_date ?? "",
      goal_initial_amount: s?.goal_initial_amount ? String(s.goal_initial_amount) : "",
      annual_deposit_goal,
      retirement_target_year,
    });
    setEditing(true);
  };

  useEffect(() => {
    if (location.state?.openEdit && !autoOpenTriggered && !isLoading && data) {
      setAutoOpenTriggered(true);
      openEdit();
    }
  }, [location.state, isLoading, data]);

  useEffect(() => {
    if (!isLoading && !autoOpenTriggered && data && !data.is_configured) {
      setAutoOpenTriggered(true);
      openEdit();
    }
  }, [isLoading, data, autoOpenTriggered]);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.put("/settings/goal", {
        monthly_deposit_amount: form.monthly_deposit_amount ? Number(form.monthly_deposit_amount) : null,
        goal_annual_return_pct: form.goal_annual_return_pct ? Number(form.goal_annual_return_pct) : null,
        goal_amount: form.goal_amount ? Number(form.goal_amount) : null,
        goal_start_date: form.goal_start_date || null,
        goal_initial_amount: form.goal_initial_amount ? Number(form.goal_initial_amount) : null,
        annual_deposit_goal: form.annual_deposit_goal ? Number(form.annual_deposit_goal) : null,
        retirement_target_year: form.retirement_target_year ? Number(form.retirement_target_year) : null,
      });
      toast("설정이 저장되었습니다", "success");
      setEditing(false);
      await invalidateDcaData(queryClient);
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(false);
    }
  };

  const s = data?.settings;
  const isConfigured = data?.is_configured;

  return (
    <div className="space-y-6">
      {isLoading && (
        <div className="flex items-center justify-center h-16 text-gray-400 dark:text-gray-500 text-sm">
          불러오는 중…
        </div>
      )}
      {isError && (
        <div className="p-3 bg-red-50 dark:bg-red-950 rounded-lg text-sm text-red-700 dark:text-red-400 flex items-center justify-between">
          <span>데이터를 불러오지 못했습니다.</span>
          <button
            onClick={() => invalidateDcaData(queryClient)}
            className="underline font-medium ml-2"
          >
            다시 시도
          </button>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">적립식 DCA 복리계산 및 월/년 목표달성율</p>
        </div>
        <button
          onClick={openEdit}
          className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <Settings2 size={15} />
          설정 편집
        </button>
      </div>

      {/* 현재 설정 요약 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">
          적립 계획 설정
        </h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">월 적립액</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {s?.monthly_deposit_amount ? fmtKrw(s.monthly_deposit_amount) : <span className="text-gray-300 dark:text-gray-600">미설정</span>}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">목표 연수익률</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {s?.goal_annual_return_pct ? `${s.goal_annual_return_pct}%` : <span className="text-gray-300 dark:text-gray-600">미설정</span>}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">목표 금액</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {s?.goal_amount ? fmtKrw(s.goal_amount) : <span className="text-gray-300 dark:text-gray-600">미설정</span>}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">투자 시작일</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {s?.goal_start_date ?? <span className="text-gray-300 dark:text-gray-600">미설정</span>}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">시작시점 자산</p>
            <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
              {s?.goal_initial_amount ? fmtKrw(s.goal_initial_amount) : <span className="text-gray-300 dark:text-gray-600">스냅샷 자동</span>}
            </p>
          </div>
        </div>
        <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
          연간 입금 목표·은퇴 목표는 대시보드에 반영됩니다.
        </p>
        {data && !isConfigured && (
          <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-950 rounded-lg text-sm text-yellow-800 dark:text-yellow-400">
            월 적립액, 목표 수익률, 목표 금액, 투자 시작일을 모두 설정해야 분석을 볼 수 있습니다.{" "}
            <button onClick={openEdit} className="underline font-medium">
              지금 설정하기
            </button>
          </div>
        )}
      </div>

      {isConfigured && data && (
        <>
          <GoalTimelineCard timeline={data.goal_timeline} goalAmount={s?.goal_amount ?? null} />
          <DCAProjectionChart data={data.projection_months} />
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:items-start">
            <YearlyAchievementTable data={data.yearly_achievements} />
            <MonthlyAchievementTable data={data.projection_months} />
          </div>
        </>
      )}

      {/* 세금 추정 섹션 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <button
          onClick={() => setShowTax((v) => !v)}
          className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-gray-800 dark:text-gray-200">세금 추정</span>
            <span className="text-xs text-gray-400 dark:text-gray-500">배당세·해외 양도세 예상 납부액</span>
          </div>
          {showTax ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
        </button>
        {showTax && (
          <div className="px-5 pb-5 space-y-4 border-t border-gray-100 dark:border-gray-800">
            <div className="flex items-center gap-3 pt-4">
              <label className="text-xs text-gray-500 dark:text-gray-400 font-medium">기준 연도</label>
              <select
                value={taxYear}
                onChange={(e) => setTaxYear(Number(e.target.value))}
                className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {[currentYear, currentYear - 1, currentYear - 2].map((y) => (
                  <option key={y} value={y}>{y}년</option>
                ))}
              </select>
            </div>

            {taxLoading && (
              <p className="text-sm text-gray-400 dark:text-gray-500">계산 중...</p>
            )}

            {taxData && !taxLoading && (
              <div className="space-y-4">
                {/* 경고 배너 */}
                {(taxData.domestic_large_holder_warning || taxData.comprehensive_tax_warning) && (
                  <div className="space-y-2">
                    {taxData.domestic_large_holder_warning && (
                      <div className="flex items-start gap-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
                        <AlertTriangle size={14} className="text-orange-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-orange-700 dark:text-orange-400">
                          국내 주식 보유액이 10억원 이상입니다. 대주주 요건 해당 시 양도소득세(22%)가 부과될 수 있습니다.
                        </p>
                      </div>
                    )}
                    {taxData.comprehensive_tax_warning && (
                      <div className="flex items-start gap-2 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                        <AlertTriangle size={14} className="text-red-500 mt-0.5 shrink-0" />
                        <p className="text-xs text-red-700 dark:text-red-400">
                          금융소득(배당+해외차익)이 2,000만원 이상입니다. 금융소득 종합과세 대상이 될 수 있습니다.
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* 세금 항목 카드 */}
                <div className="flex divide-x divide-gray-200 dark:divide-gray-700 bg-gray-50 dark:bg-gray-800 rounded-xl overflow-hidden">
                  <div className="flex-1 min-w-0 px-3 py-2.5">
                    <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">배당소득세</p>
                    <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                      {fmtKrw(taxData.dividend_tax_krw)}
                    </p>
                    <p className="hidden sm:block text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                      배당수령 {fmtKrw(taxData.dividend_income_krw)} × {taxData.rates.dividend_tax_rate_pct}%
                    </p>
                  </div>
                  <div className="flex-1 min-w-0 px-3 py-2.5">
                    <p className="text-xs text-gray-500 dark:text-gray-400 font-medium truncate">해외 양도세</p>
                    <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5 truncate">
                      {fmtKrw(taxData.overseas_tax_estimated_krw)}
                    </p>
                    <p className="hidden sm:block text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                      미실현 {fmtKrw(taxData.overseas_unrealized_gain_krw)} ({taxData.rates.overseas_tax_rate_pct}%)
                    </p>
                  </div>
                  <div className="flex-1 min-w-0 px-3 py-2.5 bg-blue-50 dark:bg-blue-900/20">
                    <p className="text-xs text-blue-600 dark:text-blue-400 font-medium truncate">예상 납부</p>
                    <p className="text-base font-bold text-blue-700 dark:text-blue-300 mt-0.5 truncate">
                      {fmtKrw(taxData.total_estimated_tax_krw)}
                    </p>
                    <p className="hidden sm:block text-xs text-blue-500 dark:text-blue-500 mt-0.5">{taxYear}년 기준</p>
                  </div>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500">{taxData.note}</p>
              </div>
            )}
            {showTax && !posLoading && positionsData && (
              <TaxPlannerSection positions={positionsData} />
            )}
          </div>
        )}
      </div>

      {/* 설정 편집 모달 */}
      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-2xl p-6 w-full max-w-md mx-4 border border-gray-200 dark:border-gray-700 max-h-[90vh] overflow-y-auto">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">투자 목표 설정</h2>

            <div className="space-y-4">
              {[
                { label: "월 적립액 (원)", key: "monthly_deposit_amount", placeholder: "500000" },
                { label: "목표 연수익률 (%)", key: "goal_annual_return_pct", placeholder: "8" },
                { label: "목표 금액 (원)", key: "goal_amount", placeholder: "500000000" },
                { label: "투자 시작일", key: "goal_start_date", placeholder: "2024-01-01", type: "date" },
                { label: "투자 시작시점 자산 (원)", key: "goal_initial_amount", placeholder: "100000000", hint: "비워두면 스냅샷 자동 사용" },
                { label: "연간 입금 목표 (원)", key: "annual_deposit_goal", placeholder: "24000000", hint: "대시보드 입금 달성률에 표시" },
                { label: "은퇴 목표시점 (연도)", key: "retirement_target_year", placeholder: "2045", hint: "대시보드 은퇴 카운트다운에 표시" },
              ].map(({ label, key, placeholder, type, hint }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{label}</label>
                  <input
                    type={type ?? "number"}
                    value={form[key as keyof GoalForm]}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {hint && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{hint}</p>}
                </div>
              ))}
            </div>

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setEditing(false)}
                className="flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                취소
              </button>
              <button
                onClick={saveSettings}
                disabled={saving}
                className="flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {saving ? "저장 중…" : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
