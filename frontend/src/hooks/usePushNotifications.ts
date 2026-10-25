/**
 * FCM 푸시 알림 등록 훅 — Capacitor 네이티브 환경에서만 동작.
 *
 * 인증 상태가 활성화될 때 권한 요청 → 토큰 등록 → 백엔드에 저장.
 * 웹/PWA 환경에서는 아무 동작 없이 종료.
 */
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import type { PluginListenerHandle } from "@capacitor/core";
import { useAuthStore } from "@/stores/authStore";
import { toast } from "@/utils/toast";
import { isNativePlatform } from "@/utils/platform";
import { registerPushToken } from "@/api/settings";
import { usePushNotificationStore } from "@/stores/pushNotificationStore";
import { rebalancingUrl } from "@/utils/rebalancingUrl";

/** 설정탭 "다시 시도" 버튼 등에서 등록을 재시도할 때 사용 — 실제 토큰 수신은 usePushNotifications()가
 * 마운트해둔 "registration" 리스너가 처리하므로, 여기서는 권한 재요청 + register() 호출만 한다. */
export async function retryPushRegistration(): Promise<void> {
  const { setStatus } = usePushNotificationStore.getState();
  if (!isNativePlatform()) {
    setStatus("unsupported");
    return;
  }
  const { PushNotifications } = await import("@capacitor/push-notifications");
  setStatus("requesting");
  const permission = await PushNotifications.requestPermissions();
  if (permission.receive !== "granted") {
    setStatus("denied");
    return;
  }
  await PushNotifications.register();
}

/** 설정탭에서 푸시 알림을 끌 때 사용 — 백엔드에 저장된 FCM 토큰을 삭제한다. */
export async function disablePushNotifications(): Promise<void> {
  const { setStatus } = usePushNotificationStore.getState();
  try {
    await registerPushToken(null);
  } finally {
    setStatus("disabled");
  }
}

/** 백엔드 push_service.py의 data.type 값 → 앱 내 딥링크 경로 매핑 (data가 없거나 알 수 없는 type이면 null). */
export function resolvePushDeepLink(
  data: Record<string, string> | undefined | null,
): string | null {
  const type = data?.type;
  if (!type) return null;

  switch (type) {
    case "REBALANCING": {
      const portfolioId = data.portfolio_id;
      return portfolioId
        ? rebalancingUrl({ tab: "포트폴리오", portfolioId, openExecution: true })
        : rebalancingUrl({ tab: "진단" });
    }
    case "REBALANCING_PLAN_PENDING":
    case "REBALANCING_EXECUTED":
    case "REBALANCING_PLAN_EXECUTION_FAILED":
      return rebalancingUrl({ tab: "이력" });
    // 세금·시장·하루 한도 게이트로 자동 실행이 보류된 알림 — 해결은 자동화 설정 조정이라 설정 모달로 연다
    // (예전엔 매핑이 없어 알림을 눌러도 앱 첫 화면에 머물렀다, plans/63 P3-4)
    case "REBALANCING_TAX_GATE_BLOCKED":
    case "REBALANCING_MARKET_GATE_BLOCKED":
    case "REBALANCING_DAILY_CAP_BLOCKED": {
      const portfolioId = data.portfolio_id;
      return portfolioId
        ? rebalancingUrl({ tab: "포트폴리오", portfolioId, openAlert: "1" })
        : rebalancingUrl({ tab: "포트폴리오" });
    }
    case "MARKET_SIGNAL":
      return rebalancingUrl({ tab: "진단" });
    case "GOAL_ASSET":
    case "GOAL_DEPOSIT":
      return `/invest-plan?tab=${encodeURIComponent("적립 계획")}`;
    case "GOAL_DIVIDEND":
      return `/invest-plan?tab=${encodeURIComponent("배당 계획")}`;
    case "DCA_CASH_SHORTFALL":
      return `/invest-plan?tab=${encodeURIComponent("적립 계획")}`;
    case "RECOMMENDATION_DRIFT":
      return rebalancingUrl({ tab: "목표 조정", mode: "추천" });
    // 전술 국면 변경 — 백엔드 push_type이 소문자(tactical_regime_check.py)라 그대로 매핑
    case "tactical_regime":
    case "tactical_dip":
      return rebalancingUrl({ tab: "목표 조정", mode: "전술" });
    default:
      return null;
  }
}

export function usePushNotifications() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();
  const setStatus = usePushNotificationStore((s) => s.setStatus);

  useEffect(() => {
    if (!isNativePlatform()) {
      setStatus("unsupported");
      return;
    }
    if (!isAuthenticated) return;

    const handles: PluginListenerHandle[] = [];
    let cancelled = false;

    async function setup() {
      const { PushNotifications } = await import("@capacitor/push-notifications");

      setStatus("requesting");
      const permission = await PushNotifications.requestPermissions();
      if (cancelled) return;
      if (permission.receive !== "granted") {
        setStatus("denied");
        return;
      }

      await PushNotifications.register();

      // FCM 토큰 수신 → 백엔드 등록
      const h1 = await PushNotifications.addListener("registration", async ({ value }) => {
        if (cancelled) return;
        try {
          await registerPushToken(value);
          setStatus("registered");
        } catch {
          // 푸시는 선택적 기능 — 실패해도 앱 동작에 영향 없음
          setStatus("error");
        }
      });

      // 앱 포그라운드 상태에서 알림 수신
      const h2 = await PushNotifications.addListener("pushNotificationReceived", (notification) => {
        if (cancelled) return;
        toast(notification.body ?? notification.title ?? "새 알림이 도착했습니다");
      });

      // 알림 탭(백그라운드/종료 상태에서 열람) → 관련 화면으로 딥링크 이동
      const h3 = await PushNotifications.addListener(
        "pushNotificationActionPerformed",
        (action) => {
          if (cancelled) return;
          const path = resolvePushDeepLink(action.notification.data);
          if (path) void navigate(path);
        },
      );

      if (!cancelled) {
        handles.push(h1, h2, h3);
      } else {
        await h1.remove();
        await h2.remove();
        await h3.remove();
      }
    }

    void setup();

    return () => {
      cancelled = true;
      handles.forEach((h) => h.remove());
    };
  }, [isAuthenticated, navigate, setStatus]);
}
