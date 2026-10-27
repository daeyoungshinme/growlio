import { useSettingsToggle } from "@/hooks/useSettingsToggle";
import { updateMarketSignalDigest } from "@/api/settings";

/** 매일 08:30 KST 시장신호 요약 알림 on/off — 등급 전환 시 즉시 알림(useCompositeSignalToggle)과 별개 설정. */
export const useMarketSignalDigestToggle = () =>
  useSettingsToggle({
    field: "market_signal_daily_digest_enabled",
    defaultValue: false,
    mutationFn: (enabled: boolean) => updateMarketSignalDigest(enabled),
  });
