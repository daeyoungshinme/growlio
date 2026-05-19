import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "../api/dashboard";
import MonthlyTrendChart from "../components/trend/MonthlyTrendChart";
import { fmtKrw, fmtMonth } from "../utils/format";

export default function TrendPage() {
  const { data, isLoading } = useQuery({ queryKey: ["dashboard"], queryFn: fetchDashboard });

  if (isLoading) return <div className="text-gray-400">로딩 중...</div>;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">자산 추이</h1>

      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-6">최근 12개월 자산 추이</h2>
        <MonthlyTrendChart data={data?.monthly_trend ?? []} />
      </div>

      <div className="bg-white rounded-2xl border border-gray-200 p-6">
        <h2 className="text-base font-semibold text-gray-800 mb-4">월별 상세</h2>
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100">
              <th className="py-2 px-3 text-left text-xs font-medium text-gray-500">월</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-500">자산 합계</th>
              <th className="py-2 px-3 text-right text-xs font-medium text-gray-500">전월 대비</th>
            </tr>
          </thead>
          <tbody>
            {(data?.monthly_trend ?? []).map((row, i, arr) => {
              const prev = arr[i - 1];
              const change = prev ? ((row.total_krw - prev.total_krw) / prev.total_krw) * 100 : null;
              return (
                <tr key={row.month} className="border-b border-gray-50">
                  <td className="py-2 px-3 text-sm">{fmtMonth(row.month)}</td>
                  <td className="py-2 px-3 text-sm text-right font-medium">
                    {fmtKrw(row.total_krw)}
                  </td>
                  <td className="py-2 px-3 text-sm text-right">
                    {change != null ? (
                      <span className={change >= 0 ? "text-red-500 font-medium" : "text-blue-500 font-medium"}>
                        {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                      </span>
                    ) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
