import { registerPlugin } from "@capacitor/core";

export interface WidgetUpdateOptions {
  totalAssets: string;
  stockReturn: string;
}

export interface WidgetPluginApi {
  update(options: WidgetUpdateOptions): Promise<void>;
}

export const WidgetPlugin = registerPlugin<WidgetPluginApi>("Widget", {
  web: {
    update: async () => {
      // 웹/PWA 환경에서는 위젯 없음 — no-op
    },
  },
});
