/**
 * FCM 푸시 알림 등록 훅 — Capacitor 네이티브 환경에서만 동작.
 *
 * 인증 상태가 활성화될 때 권한 요청 → 토큰 등록 → 백엔드에 저장.
 * 웹/PWA 환경에서는 아무 동작 없이 종료.
 */
import { useEffect } from "react";
import { Capacitor } from "@capacitor/core";
import type { PluginListenerHandle } from "@capacitor/core";
import { useAuthStore } from "@/stores/authStore";
import { toast } from "@/utils/toast";
import { registerPushToken } from "@/api/settings";

export function usePushNotifications() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!Capacitor.isNativePlatform() || !isAuthenticated) return;

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

      if (!cancelled) {
        handles.push(h1, h2);
      } else {
        await h1.remove();
        await h2.remove();
      }
    }

    setup();

    return () => {
      cancelled = true;
      handles.forEach((h) => h.remove());
    };
  }, [isAuthenticated]);
}
