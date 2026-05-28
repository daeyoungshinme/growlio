import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";
import { api } from "../api/client";
import { fetchDCAAnalysis } from "../api/invest";
import DCAProjectionChart from "../components/invest/DCAProjectionChart";
import GoalTimelineCard from "../components/invest/GoalTimelineCard";
import MonthlyAchievementTable from "../components/invest/MonthlyAchievementTable";
import YearlyAchievementTable from "../components/invest/YearlyAchievementTable";
import { fmtKrw } from "../utils/format";
import { toast } from "../utils/toast";

interface GoalForm {
  monthly_deposit_amount: string;
  goal_annual_return_pct: string;
  goal_amount: string;
  goal_start_date: string;
  goal_initial_amount: string;
}

export default function InvestPlanPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dca-analysis"],
    queryFn: fetchDCAAnalysis,
    staleTime: 60_000,
  });

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<GoalForm>({
    monthly_deposit_amount: "",
    goal_annual_return_pct: "",
    goal_amount: "",
    goal_start_date: "",
    goal_initial_amount: "",
  });

  const openEdit = () => {
    if (!data) return;
    const s = data.settings;
    setForm({
      monthly_deposit_amount: s.monthly_deposit_amount ? String(s.monthly_deposit_amount) : "",
      goal_annual_return_pct: s.goal_annual_return_pct ? String(s.goal_annual_return_pct) : "",
      goal_amount: s.goal_amount ? String(s.goal_amount) : "",
      goal_start_date: s.goal_start_date ?? "",
      goal_initial_amount: s.goal_initial_amount ? String(s.goal_initial_amount) : "",
    });
    setEditing(true);
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.put("/settings/goal", {
        monthly_deposit_amount: form.monthly_deposit_amount ? Number(form.monthly_deposit_amount) : null,
        goal_annual_return_pct: form.goal_annual_return_pct ? Number(form.goal_annual_return_pct) : null,
        goal_amount: form.goal_amount ? Number(form.goal_amount) : null,
        goal_start_date: form.goal_start_date || null,
        goal_initial_amount: form.goal_initial_amount ? Number(form.goal_initial_amount) : null,
      });
      toast("설정이 저장되었습니다", "success");
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["dca-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400 dark:text-gray-500 text-sm">
        불러오는 중…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center justify-center h-64 text-red-500 text-sm">
        데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
      </div>
    );
  }

  const s = data?.settings;
  const isConfigured = data?.is_configured;

  return (
    <div className="space-y-6">
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
        {!isConfigured && (
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

      {/* 설정 편집 모달 */}
      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-900 rounded-2xl p-6 w-full max-w-md space-y-4 mx-4 border border-gray-200 dark:border-gray-700">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">적립 계획 설정</h2>

            {[
              { label: "월 적립액 (원)", key: "monthly_deposit_amount", placeholder: "500000" },
              { label: "목표 연수익률 (%)", key: "goal_annual_return_pct", placeholder: "8" },
              { label: "목표 금액 (원)", key: "goal_amount", placeholder: "500000000" },
              { label: "투자 시작일", key: "goal_start_date", placeholder: "2024-01-01", type: "date" },
              { label: "투자 시작시점 자산 (원)", key: "goal_initial_amount", placeholder: "100000000" },
            ].map(({ label, key, placeholder, type }) => (
              <div key={key}>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">{label}</label>
                <input
                  type={type ?? "number"}
                  value={form[key as keyof GoalForm]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder}
                  className="w-full border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            ))}

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
