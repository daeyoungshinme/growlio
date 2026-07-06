import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { fetchCompositeSignalStatus } from "@/api/rebalancing";
import { updateCompositeSignalAlerts } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { invalidateCompositeSignalData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";
import { SectionCard } from "./shared";

export function MarketSignalAlertSection() {
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
    onError: (e) => toast(extractErrorMessage(e, "설정 저장에 실패했습니다"), "error"),
  });

  return (
    <SectionCard title="시장 신호 알림">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        포트폴리오 목표 비중 이탈이 없어도, 시장 상황이나 리스크가 심상치 않으면 이메일·푸시로
        알려드립니다.
      </p>
      <ul className="text-xs text-gray-500 dark:text-gray-400 space-y-1.5 list-disc pl-4">
        <li>
          시장 위험 신호 등급이 바뀔 때(안정↔주의↔위험) 즉시 알려드립니다. 1시간마다 점검하며,
          실제로 등급이 바뀔 때만 발송되므로 며칠간 안 올 수도, 급변장에서는 여러 번 올 수도
          있습니다.
        </li>
        <li>
          이탈이 없어도 위험 신호가 높거나 포트폴리오 리스크가 과도하면, 하루 최대 1회 점검 권장
          메일을 별도로 보내드립니다.
        </li>
      </ul>

      {status && (
        <>
          <div className="flex items-center gap-3 pt-1">
            <label className="relative inline-flex items-center cursor-pointer shrink-0">
              <input
                type="checkbox"
                checked={status.enabled}
                disabled={toggleMut.isPending}
                onChange={(e) => toggleMut.mutate(e.target.checked)}
                className="sr-only peer"
                aria-label="시장/리스크 신호 알림 받기"
              />
              <div className="w-9 h-5 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full" />
            </label>
            <span className="text-sm text-gray-700 dark:text-gray-300">
              {status.enabled ? "알림 받는 중" : "알림 꺼짐"}
            </span>
          </div>

          <p className="text-xs text-gray-500 dark:text-gray-400">
            {status.triggered && status.reason
              ? status.reason
              : status.enabled
                ? "현재는 이탈이 없어도 알림이 발송될 조건이 아닙니다"
                : "알림이 꺼져 있어 신호를 평가하지 않습니다"}
          </p>

          {status.enabled && !status.has_active_alert && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-50 border border-amber-200 dark:bg-amber-950/40 dark:border-amber-800/40">
              <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-700 dark:text-amber-300">
                현재 활성화된 리밸런싱 알림이 없어 이 알림을 받을 수 없습니다.{" "}
                <Link to="/rebalancing?rtab=포트폴리오" className="underline font-medium">
                  리밸런싱 탭에서 설정하기
                </Link>
              </p>
            </div>
          )}
        </>
      )}

      <p className="text-xs text-gray-400 dark:text-gray-500">
        최근 발송 이력은 발송 이력 탭에서 확인할 수 있습니다.
      </p>
    </SectionCard>
  );
}
