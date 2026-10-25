import { useEffect } from "react";
import { hashKey, useQueryClient } from "@tanstack/react-query";
import type { DashboardData } from "@/api/dashboard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { fmtKrwShort, fmtPct } from "@/utils/format";
import { isNativePlatform } from "@/utils/platform";

async function pushToWidget(snapshot: DashboardData) {
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

// 앱 데이터가 갱신될 때마다 Android 홈 화면 위젯 데이터를 SharedPreferences로 동기화한다.
// 위젯은 GrowlioWidget.java (AppWidgetProvider)가 직접 읽어 렌더링한다.
// useQuery 대신 캐시를 구독만 한다 — 상시 마운트된 observer가 있으면 대시보드가 꺼둔
// refetchOnWindowFocus를 무력화해 앱 복귀·무효화 때마다 /dashboard를 어느 페이지에서든 다시 불렀다.
// 데이터는 부팅 프리페치(App.tsx)와 홈 화면이 채운다.
export function useWidget() {
  const native = isNativePlatform();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!native) return;
    const dashboardHash = hashKey(QUERY_KEYS.dashboard);
    let last: DashboardData | undefined;
    const sync = () => {
      const data = queryClient.getQueryData<DashboardData>(QUERY_KEYS.dashboard);
      if (!data || data === last) return;
      last = data;
      void pushToWidget(data);
    };
    sync();
    return queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && event.query.queryHash === dashboardHash) sync();
    });
  }, [native, queryClient]);
}
