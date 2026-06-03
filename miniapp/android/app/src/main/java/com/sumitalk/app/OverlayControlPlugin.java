package com.sumitalk.app;

import android.Manifest;
import android.app.AppOpsManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.ContentUris;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;
import android.provider.AlarmClock;
import android.provider.CalendarContract;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.UUID;

@CapacitorPlugin(name = "SumiOverlay")
public class OverlayControlPlugin extends Plugin {
    private static final String PREF_NATIVE_DEVICE = "native_device_id";
    private static final String SYSTEM_ALARM_CHANNEL_ID = "sumitalk_system_alarm";

    @PluginMethod
    public void setFloatingBallEnabled(PluginCall call) {
        boolean enabled = call.getBoolean("enabled", true);
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putBoolean(FloatingBallService.PREF_OVERLAY_VISIBLE, enabled)
                .apply();
        Intent intent = new Intent(ctx, FloatingBallService.class);
        intent.setAction(FloatingBallService.ACTION_START_OR_UPDATE);
        ContextCompat.startForegroundService(ctx, intent);
        call.resolve();
    }

    @PluginMethod
    public void getFloatingBallEnabled(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        boolean enabled =
                ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                        .getBoolean(FloatingBallService.PREF_OVERLAY_VISIBLE, true);
        JSObject o = new JSObject();
        o.put("enabled", enabled);
        call.resolve(o);
    }

    @PluginMethod
    public void getHealthReportingStatus(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        JSObject o = new JSObject();
        o.put("intervalSeconds", SumiNotificationListenerService.getHealthReportIntervalSeconds(ctx));
        o.put("packageName", SumiNotificationListenerService.NOTIFY_FOR_XIAOMI_PACKAGE);
        o.put("listenerEnabled", isNotificationListenerEnabled(ctx));
        o.put("listenerConnected", SumiNotificationListenerService.isListenerConnected());
        JSONObject last = SumiNotificationListenerService.getLastHealthPayload(ctx);
        JSONArray logs = SumiNotificationListenerService.getHealthReportLogs(ctx);
        o.put("last", last);
        o.put("logs", logs);
        call.resolve(o);
    }

    @PluginMethod
    public void setHealthReportingConfig(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        Integer intervalSeconds = call.getInt("intervalSeconds");
        if (intervalSeconds == null) {
            call.reject("invalid_interval");
            return;
        }
        SumiNotificationListenerService.setHealthReportIntervalSeconds(ctx, intervalSeconds);
        JSObject o = new JSObject();
        o.put("intervalSeconds", SumiNotificationListenerService.getHealthReportIntervalSeconds(ctx));
        call.resolve(o);
    }

    @PluginMethod
    public void requestHealthReportingSnapshot(PluginCall call) {
        SumiNotificationListenerService.requestActiveNotificationSnapshot();
        JSObject o = new JSObject();
        o.put("requested", SumiNotificationListenerService.isListenerConnected());
        call.resolve(o);
    }

    @PluginMethod
    public void clearHealthReportingLogs(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putString(SumiNotificationListenerService.PREF_HEALTH_REPORT_LOGS_JSON, "[]")
                .apply();
        call.resolve();
    }

    @PluginMethod
    public void showDuVitalsNotification(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        int heartBpm = positiveIntFromCall(call, "heartBpm", "heart_bpm");
        int breathRpm = positiveIntFromCall(call, "breathRpm", "breath_rpm");
        String status = String.valueOf(call.getString("status", "")).trim();
        String updatedAt = String.valueOf(call.getString("updatedAt", call.getString("updated_at", ""))).trim();
        boolean shown = DuVitalsNotification.show(ctx, heartBpm, breathRpm, status, updatedAt);
        JSObject o = new JSObject();
        o.put("shown", shown);
        call.resolve(o);
    }

    @PluginMethod
    public void clearDuVitalsNotification(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        DuVitalsNotification.cancel(ctx);
        call.resolve();
    }

    @PluginMethod
    public void openNotificationListenerSettings(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        try {
            ctx.startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            call.resolve();
        } catch (Exception e) {
            call.reject("open_notification_listener_settings_failed", e);
        }
    }

    @PluginMethod
    public void getStableDeviceId(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        JSObject o = new JSObject();
        o.put("deviceId", resolveStableDeviceId(ctx));
        call.resolve(o);
    }

    @PluginMethod
    public void getSenseReportingStatus(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        JSObject o = new JSObject();
        o.put("enabled", FloatingBallService.isSenseReportingEnabled(ctx));
        o.put("deviceId", resolveStableDeviceId(ctx));
        o.put("accessibilityEnabled", isSumiAccessibilityEnabled(ctx));
        o.put("locationPermission", hasLocationPermission(ctx));
        o.put("usageStatsAvailable", hasUsageStatsPermission(ctx));
        call.resolve(o);
    }

    @PluginMethod
    public void setSenseReportingConfig(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        boolean enabled = call.getBoolean("enabled", true);
        FloatingBallService.setSenseReportingEnabled(ctx, enabled);
        if (enabled) {
            Intent intent = new Intent(ctx, FloatingBallService.class);
            intent.setAction(FloatingBallService.ACTION_REQUEST_SENSE_SNAPSHOT);
            ContextCompat.startForegroundService(ctx, intent);
        }
        JSObject o = new JSObject();
        o.put("enabled", FloatingBallService.isSenseReportingEnabled(ctx));
        call.resolve(o);
    }

    @PluginMethod
    public void requestSenseReportingSnapshot(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        boolean enabled = FloatingBallService.isSenseReportingEnabled(ctx);
        if (!enabled) {
            JSObject o = new JSObject();
            o.put("requested", false);
            o.put("foregroundRequested", false);
            o.put("usageRequested", false);
            call.resolve(o);
            return;
        }
        Intent intent = new Intent(ctx, FloatingBallService.class);
        intent.setAction(FloatingBallService.ACTION_REQUEST_SENSE_SNAPSHOT);
        ContextCompat.startForegroundService(ctx, intent);
        boolean foregroundRequested = SumiAccessibilityService.requestForegroundSnapshot();
        boolean usageRequested = false;
        try {
            if (getActivity() instanceof MainActivity) {
                ((MainActivity) getActivity()).requestUsageStatsSnapshot();
                usageRequested = true;
            }
        } catch (Exception ignored) {
        }
        JSObject o = new JSObject();
        o.put("requested", true);
        o.put("foregroundRequested", foregroundRequested);
        o.put("usageRequested", usageRequested);
        call.resolve(o);
    }

    @PluginMethod
    public void createSystemAlarm(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        Integer hour = call.getInt("hour");
        Integer minute = call.getInt("minute");
        if (hour == null || hour < 0 || hour > 23) {
            call.reject("invalid_hour");
            return;
        }
        if (minute == null || minute < 0 || minute > 59) {
            call.reject("invalid_minute");
            return;
        }

        String title = String.valueOf(call.getString("title", "渡的提醒")).trim();
        if (title.isEmpty()) {
            title = "渡的提醒";
        }
        boolean skipUi = call.getBoolean("skipUi", true);
        boolean notify = call.getBoolean("notify", !isAppVisible(ctx));

        Intent intent =
                new Intent(AlarmClock.ACTION_SET_ALARM)
                        .putExtra(AlarmClock.EXTRA_HOUR, hour)
                        .putExtra(AlarmClock.EXTRA_MINUTES, minute)
                        .putExtra(AlarmClock.EXTRA_MESSAGE, title)
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, skipUi)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            ctx.startActivity(intent);
            if (notify) {
                showSystemAlarmCreatedNotification(ctx, hour, minute, title);
            }
            JSObject o = new JSObject();
            o.put("ok", true);
            o.put("hour", hour);
            o.put("minute", minute);
            o.put("title", title);
            o.put("notified", notify);
            call.resolve(o);
        } catch (Exception e) {
            call.reject("create_system_alarm_failed", e);
        }
    }

    @PluginMethod
    public void openSystemAlarms(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        try {
            ctx.startActivity(buildOpenSystemAlarmsIntent());
            call.resolve();
        } catch (Exception e) {
            call.reject("open_system_alarms_failed", e);
        }
    }

    @PluginMethod
    public void openCalendarEvent(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        long eventId = 0L;
        long startMillis = 0L;
        try {
            if (call.getData() != null) {
                eventId = call.getData().optLong("eventId", 0L);
                startMillis = call.getData().optLong("startMillis", 0L);
            }
        } catch (Exception ignored) {
        }
        try {
            ctx.startActivity(buildOpenCalendarEventIntent(eventId, startMillis));
            call.resolve();
        } catch (Exception e) {
            call.reject("open_calendar_event_failed", e);
        }
    }

    private boolean isAppVisible(Context ctx) {
        try {
            return ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                    .getBoolean(FloatingBallService.PREF_APP_VISIBLE, false);
        } catch (Exception ignored) {
            return false;
        }
    }

    private boolean isNotificationListenerEnabled(Context ctx) {
        try {
            String enabled = Settings.Secure.getString(ctx.getContentResolver(), "enabled_notification_listeners");
            if (enabled == null || enabled.trim().isEmpty()) return false;
            ComponentName target = new ComponentName(ctx, SumiNotificationListenerService.class);
            String targetPackage = ctx.getPackageName();
            String targetClass = target.getClassName();
            for (String item : enabled.split(":")) {
                ComponentName component = ComponentName.unflattenFromString(item);
                if (component == null) continue;
                if (targetPackage.equals(component.getPackageName()) && targetClass.equals(component.getClassName())) {
                    return true;
                }
            }
            String lower = enabled.toLowerCase(java.util.Locale.US);
            return lower.contains(target.flattenToString().toLowerCase(java.util.Locale.US))
                    || lower.contains(target.flattenToShortString().toLowerCase(java.util.Locale.US));
        } catch (Exception e) {
            return false;
        }
    }

    private boolean isSumiAccessibilityEnabled(Context ctx) {
        try {
            String enabled = Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (enabled == null || enabled.trim().isEmpty()) return false;
            ComponentName target = new ComponentName(ctx, SumiAccessibilityService.class);
            String targetPackage = ctx.getPackageName();
            String targetClass = target.getClassName();
            for (String item : enabled.split(":")) {
                ComponentName component = ComponentName.unflattenFromString(item);
                if (component == null) continue;
                if (targetPackage.equals(component.getPackageName()) && targetClass.equals(component.getClassName())) {
                    return true;
                }
            }
            String lower = enabled.toLowerCase(java.util.Locale.US);
            return lower.contains(target.flattenToString().toLowerCase(java.util.Locale.US))
                    || lower.contains(target.flattenToShortString().toLowerCase(java.util.Locale.US));
        } catch (Exception e) {
            return false;
        }
    }

    private boolean hasLocationPermission(Context ctx) {
        return ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || ContextCompat.checkSelfPermission(ctx, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasUsageStatsPermission(Context ctx) {
        try {
            AppOpsManager appOps = (AppOpsManager) ctx.getSystemService(Context.APP_OPS_SERVICE);
            if (appOps == null) return false;
            int mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), ctx.getPackageName());
            return mode == AppOpsManager.MODE_ALLOWED;
        } catch (Exception ignored) {
            return false;
        }
    }

    private int positiveIntFromCall(PluginCall call, String... keys) {
        if (call == null || call.getData() == null) return 0;
        for (String key : keys) {
            try {
                Object raw = call.getData().opt(key);
                int value = 0;
                if (raw instanceof Number) {
                    value = ((Number) raw).intValue();
                } else if (raw != null) {
                    value = Integer.parseInt(String.valueOf(raw).trim());
                }
                if (value > 0) return value;
            } catch (Exception ignored) {
            }
        }
        return 0;
    }

    private Intent buildOpenSystemAlarmsIntent() {
        return new Intent(AlarmClock.ACTION_SHOW_ALARMS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    private Intent buildOpenCalendarEventIntent(long eventId, long startMillis) {
        Uri uri = eventId > 0L
                ? ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eventId)
                : Uri.parse("content://com.android.calendar/time/" + Math.max(1L, startMillis));
        return new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    private void showSystemAlarmCreatedNotification(Context ctx, int hour, int minute, String title) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        createSystemAlarmNotificationChannel(ctx);
        PendingIntent pi =
                PendingIntent.getActivity(
                        ctx,
                        (int) (System.currentTimeMillis() & 0x7fffffff),
                        buildOpenSystemAlarmsIntent(),
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String time = String.format(java.util.Locale.US, "%02d:%02d", hour, minute);
        Notification notification =
                new NotificationCompat.Builder(ctx, SYSTEM_ALARM_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle("已创建系统闹钟")
                        .setContentText(time + " · " + title)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(time + " · " + title))
                        .setContentIntent(pi)
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setCategory(NotificationCompat.CATEGORY_ALARM)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .build();
        try {
            NotificationManagerCompat.from(ctx)
                    .notify((int) (System.currentTimeMillis() & 0x7fffffff), notification);
        } catch (Exception ignored) {
        }
    }

    private void createSystemAlarmNotificationChannel(Context ctx) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel channel =
                new NotificationChannel(SYSTEM_ALARM_CHANNEL_ID, "SumiTalk 系统闹钟", NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("用于显示系统闹钟创建结果");
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        nm.createNotificationChannel(channel);
    }

    private String resolveStableDeviceId(Context ctx) {
        try {
            String androidId =
                    String.valueOf(Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ANDROID_ID))
                            .trim();
            if (!androidId.isEmpty() && !"9774d56d682e549c".equals(androidId)) {
                return "android_" + androidId.toLowerCase();
            }
        } catch (Exception ignored) {
        }

        SharedPreferences sp = ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE);
        String existing = String.valueOf(sp.getString(PREF_NATIVE_DEVICE, "")).trim();
        if (!existing.isEmpty()) {
            return existing;
        }
        String next = "native_" + UUID.randomUUID().toString().replace("-", "");
        sp.edit().putString(PREF_NATIVE_DEVICE, next).apply();
        return next;
    }
}
