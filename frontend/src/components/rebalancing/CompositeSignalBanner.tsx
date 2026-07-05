import { ShieldAlert, TrendingUp } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCompositeSignalStatus } from "@/api/rebalancing";
import { updateCompositeSignalAlerts } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateCompositeSignalData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 진단탭 상단에 단 1회만 표시되는 시장/리스크 복합신호 배너 — 유저 단위 신호이므로 포트폴리오별로 반복하지 않는다. */
export default function CompositeSignalBanner() {
  const qc = useQueryClient();

  const { data: status } = useQuery({
    queryKey: QUERY_KEYS.compositeSignalStatus,
    queryFn: fetchCompositeSignalStatus,
    staleTime: STALE_TIME.LONG,
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) => updateCompositeSignalAlerts(enabled),
    onSuccess: () => {
      void invalidateCompositeSignalData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다")),
  });

  if (!status) return null;

  return (
    <div
      className={`rounded-xl border p-4 ${
        status.triggered
          ? "bg-indigo-50 border-indigo-200 dark:bg-indigo-950/40 dark:border-indigo-800/40"
          : "bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700"
      }`}
    >
      <div className="flex items-start gap-3">
        {status.triggered ? (
          <div className="flex items-center gap-1.5 shrink-0">
            <TrendingUp size={16} className="text-indigo-500" />
            <ShieldAlert size={16} className="text-indigo-500" />
          </div>
        ) : (
          <ShieldAlert size={16} className="text-gray-400 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 dark:text-gray-200">시장/리스크 신호</p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {status.triggered && status.reason
              ? status.reason
              : status.enabled
                ? "현재 특이사항이 없습니다"
                : "알림이 꺼져 있어 신호를 평가하지 않습니다"}
          </p>
        </div>
        <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-0.5">
          <input
            type="checkbox"
            checked={status.enabled}
            disabled={toggleMut.isPending}
            onChange={(e) => toggleMut.mutate(e.target.checked)}
            className="sr-only peer"
            aria-label="시장/리스크 신호 알림 받기"
          />
          <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
        </label>
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
        이탈이 없어도 시장 위험 신호가 RED이거나 리스크가 집중되어 있으면 점검을 권장하는 알림을
        이메일/푸시로 추가로 받습니다. 계정 전체 기준 신호이므로 포트폴리오와 무관하게 하나로
        표시됩니다.
      </p>
    </div>
  );
}
