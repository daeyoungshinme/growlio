import { memo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { fetchDartDisclosures } from "@/api/dart";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { getHttpStatus } from "@/utils/error";

const DAYS_OPTIONS = [
  { label: "7일", value: 7 },
  { label: "30일", value: 30 },
  { label: "90일", value: 90 },
];

function formatDate(rcept_dt: string): string {
  if (rcept_dt.length !== 8) return rcept_dt;
  return `${rcept_dt.slice(0, 4)}.${rcept_dt.slice(4, 6)}.${rcept_dt.slice(6, 8)}`;
}

function DisclosureFeedCard() {
  const [days, setDays] = useState(30);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: QUERY_KEYS.dartDisclosures(days),
    queryFn: () => fetchDartDisclosures(days),
    staleTime: STALE_TIME.LONG,
    retry: false,
  });

  const isDartKeyMissing =
    isError && getHttpStatus(error) === 422;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <FileText size={16} className="text-gray-400 dark:text-gray-500" />
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">보유 종목 공시</h2>
        </div>
        <div className="flex gap-1">
          {DAYS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setDays(opt.value)}
              className={`px-2 py-1 text-xs rounded-md transition-colors ${
                days === opt.value
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 font-medium"
                  : "text-gray-400 dark:text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {isDartKeyMissing ? (
        <div className="py-6 text-center">
          <p className="text-sm text-gray-400 dark:text-gray-500 mb-3">
            DART API 키를 설정하면 보유 종목의 공시를 확인할 수 있습니다.
          </p>
          <Link
            to="/settings"
            className="inline-block px-4 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            설정에서 연결하기
          </Link>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse flex gap-3">
              <div className="w-16 h-3.5 bg-gray-100 dark:bg-gray-800 rounded" />
              <div className="flex-1 h-3.5 bg-gray-100 dark:bg-gray-800 rounded" />
            </div>
          ))}
        </div>
      ) : !data || data.length === 0 ? (
        <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-6">
          최근 {days}일간 공시가 없습니다.
        </p>
      ) : (
        <div className="space-y-0 max-h-72 overflow-y-auto">
          {data.map((item) => (
            <a
              key={item.rcept_no}
              href={item.dart_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-3 py-2.5 border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded-lg px-2 -mx-2 transition-colors group"
            >
              <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap mt-0.5 w-20 shrink-0">
                {formatDate(item.rcept_dt)}
              </span>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-medium text-blue-600 dark:text-blue-400 mr-1.5">
                  {item.corp_name}
                </span>
                <span className="text-xs text-gray-700 dark:text-gray-300 leading-tight">
                  {item.report_nm}
                </span>
                {item.rm && (
                  <span className="ml-1 text-xs text-orange-500 dark:text-orange-400">
                    [{item.rm}]
                  </span>
                )}
              </div>
              <ExternalLink
                size={12}
                className="text-gray-300 dark:text-gray-600 group-hover:text-blue-500 shrink-0 mt-0.5 transition-colors"
              />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(DisclosureFeedCard);
