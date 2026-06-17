import { useCallback } from "react";

type HapticType = "light" | "medium" | "heavy" | "success" | "error";

export async function triggerHaptic(type: HapticType): Promise<void> {
  try {
    const { Haptics, ImpactStyle, NotificationType } = await import("@capacitor/haptics");
    if (type === "success") {
      await Haptics.notification({ type: NotificationType.Success });
    } else if (type === "error") {
      await Haptics.notification({ type: NotificationType.Error });
    } else {
      const styleMap: Record<string, (typeof ImpactStyle)[keyof typeof ImpactStyle]> = {
        light: ImpactStyle.Light,
        medium: ImpactStyle.Medium,
        heavy: ImpactStyle.Heavy,
      };
      await Haptics.impact({ style: styleMap[type] ?? ImpactStyle.Medium });
    }
  } catch {
    // 브라우저/PWA 환경에서 Capacitor 미지원 — 무시
  }
}

export function useHaptic() {
  const impact = useCallback((type: HapticType = "medium") => {
    void triggerHaptic(type);
  }, []);
  return { impact };
}
