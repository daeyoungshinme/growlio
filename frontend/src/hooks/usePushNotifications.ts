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
        ? `/rebalancing?rtab=포트폴리오&portfolioId=${portfolioId}&openExecution=1`
        : "/rebalancing?rtab=진단";
    }
    case "REBALANCING_PLAN_PENDING":
    case "REBALANCING_EXECUTED":
      return "/rebalancing?rtab=이력";
    case "MARKET_SIGNAL":
      return "/rebalancing?rtab=진단";
    default:
      return null;
  }
}

export function usePushNotifications() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  useEffect(() => {
    if (!isNativePlatform() || !isAuthenticated) return;

    const handles: PluginListenerHandle[] = [];
    let cancelled = false;

    async function setup() {
      const { PushNotifications } = await import("@capacitor/push-notifications");

      const permission = await PushNotifications.requestPermissions();
      if (cancelled || permission.receive !== "granted") return;

      await PushNotifications.register();

      // FCM 토큰 수신 → 백엔드 등록
      const h1 = await PushNotifications.addListener("registration", async ({ value }) => {
        if (cancelled) return;
        try {
          await registerPushToken(value);
        } catch {
          // 푸시는 선택적 기능 — 실패해도 앱 동작에 영향 없음
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
          if (path) navigate(path);
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
  }, [isAuthenticated, navigate]);
}
