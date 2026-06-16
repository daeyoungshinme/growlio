package com.growlio.app;

import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "Widget")
public class WidgetPlugin extends Plugin {

    @PluginMethod
    public void update(PluginCall call) {
        String totalAssets = call.getString("totalAssets", "—");
        String stockReturn = call.getString("stockReturn", "—");

        Context context = getContext();
        SharedPreferences prefs = context.getSharedPreferences(
            GrowlioWidget.PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
            .putString(GrowlioWidget.KEY_TOTAL_ASSETS, totalAssets)
            .putString(GrowlioWidget.KEY_STOCK_RETURN, stockReturn)
            .apply();

        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName component = new ComponentName(context, GrowlioWidget.class);
        int[] ids = manager.getAppWidgetIds(component);
        GrowlioWidget.updateWidgets(context, manager, ids);

        call.resolve();
    }
}
