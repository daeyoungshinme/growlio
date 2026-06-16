import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/dashboard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { fmtKrwShort, fmtPct } from "@/utils/format";
import { isNativePlatform } from "@/utils/platform";

// 앱 데이터가 갱신될 때마다 Android 홈 화면 위젯 데이터를 SharedPreferences로 동기화한다.
// 위젯은 GrowlioWidget.java (AppWidgetProvider)가 직접 읽어 렌더링한다.
export function useWidget() {
  const native = isNativePlatform();

  const { data } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    enabled: native,
    staleTime: 5 * 60 * 1000,
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
