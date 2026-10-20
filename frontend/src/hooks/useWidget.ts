import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/dashboard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { fmtKrwShort, fmtPct } from "@/utils/format";
import { isNativePlatform } from "@/utils/platform";
import { STALE_TIME } from "@/constants/queryConfig";
import { useAuthStore } from "@/stores/authStore";

// 앱 데이터가 갱신될 때마다 Android 홈 화면 위젯 데이터를 SharedPreferences로 동기화한다.
// 위젯은 GrowlioWidget.java (AppWidgetProvider)가 직접 읽어 렌더링한다.
export function useWidget() {
  const native = isNativePlatform();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const { data } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    // 로그아웃 상태(로그인·가입 화면)에서 조회하면 401 → "세션 만료" 토스트가 뜬다
    enabled: native && isAuthenticated,
    staleTime: STALE_TIME.FIVE_MINUTES,
  });

  useEffect(() => {
    if (!native || !data) return;

    const snapshot = data;
    async function sync() {
      try {
        const { WidgetPlugin } = await import("@/plugins/WidgetPlugin");
        await WidgetPlugin.update({
          totalAssets: fmtKrwShort(snapshot.total_assets_krw),
          stockReturn: fmtPct(snapshot.stock_return_pct),
        });
      } catch {
        // 위젯 미설치 또는 플러그인 미사용 환경에서는 무시
      }
    }
    void sync();
  }, [native, data]);
}
