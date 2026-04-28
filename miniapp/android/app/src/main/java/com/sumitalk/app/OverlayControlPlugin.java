package com.sumitalk.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.provider.Settings;
import android.provider.AlarmClock;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
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

    private boolean isAppVisible(Context ctx) {
        try {
            return ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                    .getBoolean(FloatingBallService.PREF_APP_VISIBLE, false);
        } catch (Exception ignored) {
            return false;
        }
    }

    private Intent buildOpenSystemAlarmsIntent() {
        return new Intent(AlarmClock.ACTION_SHOW_ALARMS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
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
