import { useCompositeSignalToggle } from "@/hooks/useCompositeSignalToggle";
import { useMarketSignalDigestToggle } from "@/hooks/useMarketSignalDigestToggle";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import { SectionCard } from "./shared";

export function MarketSignalAlertSection() {
  const { status, toggle, isPending } = useCompositeSignalToggle();
  const {
    enabled: digestEnabled,
    toggle: toggleDigest,
    isPending: digestPending,
  } = useMarketSignalDigestToggle();

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
            <ToggleSwitch
              checked={status.enabled}
              disabled={isPending}
              onChange={toggle}
              ariaLabel="시장/리스크 신호 알림 받기"
            />
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
        </>
      )}

      <div className="border-t border-gray-100 dark:border-gray-800 pt-3 mt-1">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          매일 08:30 현재 시장 위험 신호를 등급 변화와 무관하게 요약해 보내드립니다.
        </p>
        <div className="flex items-center gap-3 pt-2">
          <ToggleSwitch
            checked={digestEnabled}
            disabled={digestPending}
            onChange={toggleDigest}
            ariaLabel="매일 아침 시장신호 요약"
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            {digestEnabled ? "매일 아침 시장신호 요약 받는 중" : "매일 아침 시장신호 요약 꺼짐"}
          </span>
        </div>
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500">
        최근 발송 이력은 발송 이력 탭에서 확인할 수 있습니다.
      </p>
    </SectionCard>
  );
}
