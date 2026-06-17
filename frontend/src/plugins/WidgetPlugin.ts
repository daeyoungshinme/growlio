import { registerPlugin } from "@capacitor/core";

export interface WidgetUpdateOptions {
  totalAssets: string;
  stockReturn: string;
}

export interface WidgetPlugin {
  update(options: WidgetUpdateOptions): Promise<void>;
}

// eslint-disable-next-line no-redeclare
export const WidgetPlugin = registerPlugin<WidgetPlugin>("Widget", {
  web: {
    update: async () => {
      // 웹/PWA 환경에서는 위젯 없음 — no-op
    },
  },
});
