package com.growlio.app;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.SharedPreferences;
import android.widget.RemoteViews;

public class GrowlioWidget extends AppWidgetProvider {
    static final String PREFS_NAME = "growlio_widget";
    static final String KEY_TOTAL_ASSETS = "total_assets";
    static final String KEY_STOCK_RETURN = "stock_return";

    @Override
    public void onUpdate(Context context, AppWidgetManager appWidgetManager, int[] appWidgetIds) {
        updateWidgets(context, appWidgetManager, appWidgetIds);
    }

    static void updateWidgets(Context context, AppWidgetManager manager, int[] ids) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        String totalAssets = prefs.getString(KEY_TOTAL_ASSETS, "—");
        String stockReturn = prefs.getString(KEY_STOCK_RETURN, "—");

        for (int id : ids) {
            RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.widget_layout);
            views.setTextViewText(R.id.widget_total_assets, totalAssets);
            views.setTextViewText(R.id.widget_daily_return, stockReturn);
            manager.updateAppWidget(id, views);
        }
    }
}
