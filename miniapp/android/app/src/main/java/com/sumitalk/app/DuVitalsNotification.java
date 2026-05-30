package com.sumitalk.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

final class DuVitalsNotification {
    private static final String CHANNEL_ID = "sumitalk_du_vitals";
    private static final int NOTIFICATION_ID = 2302;

    private DuVitalsNotification() {}

    static boolean show(Context ctx, int heartBpm, int breathRpm, String status, String updatedAt) {
        if (ctx == null || (heartBpm <= 0 && breathRpm <= 0) || !canPostNotifications(ctx)) {
            return false;
        }
        createChannel(ctx);
        String content = buildContentText(heartBpm, breathRpm);
        String detail = buildDetailText(status, updatedAt);
        PendingIntent pi =
                PendingIntent.getActivity(
                        ctx,
                        NOTIFICATION_ID,
                        buildOpenAppIntent(ctx),
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification =
                new NotificationCompat.Builder(ctx, CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle("渡的心跳")
                        .setContentText(content)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(detail.isEmpty() ? content : content + "\n" + detail))
                        .setContentIntent(pi)
                        .setOngoing(true)
                        .setAutoCancel(false)
                        .setOnlyAlertOnce(true)
                        .setSilent(true)
                        .setPriority(NotificationCompat.PRIORITY_LOW)
                        .setCategory(NotificationCompat.CATEGORY_STATUS)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .setShowWhen(false)
                        .build();
        try {
            NotificationManagerCompat.from(ctx).notify(NOTIFICATION_ID, notification);
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    static void cancel(Context ctx) {
        if (ctx == null) return;
        try {
            NotificationManagerCompat.from(ctx).cancel(NOTIFICATION_ID);
        } catch (Exception ignored) {
        }
    }

    private static boolean canPostNotifications(Context ctx) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
                || ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED;
    }

    private static void createChannel(Context ctx) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm == null) return;
        NotificationChannel channel =
                new NotificationChannel(CHANNEL_ID, "渡的心跳", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("显示渡的拟态心率和呼吸状态");
        channel.setShowBadge(false);
        channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        nm.createNotificationChannel(channel);
    }

    private static Intent buildOpenAppIntent(Context ctx) {
        Intent openIntent = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        if (openIntent == null) {
            openIntent = new Intent(ctx, MainActivity.class);
        }
        return openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    }

    private static String buildContentText(int heartBpm, int breathRpm) {
        StringBuilder sb = new StringBuilder();
        if (heartBpm > 0) {
            sb.append("心率 ").append(heartBpm).append(" bpm");
        }
        if (breathRpm > 0) {
            if (sb.length() > 0) sb.append(" · ");
            sb.append("呼吸 ").append(breathRpm).append("/min");
        }
        return sb.toString();
    }

    private static String buildDetailText(String status, String updatedAt) {
        StringBuilder sb = new StringBuilder();
        String st = String.valueOf(status == null ? "" : status).trim();
        if (!st.isEmpty()) {
            sb.append("状态 ").append(st);
        }
        String time = compactTime(updatedAt);
        if (!time.isEmpty()) {
            if (sb.length() > 0) sb.append(" · ");
            sb.append("同步 ").append(time);
        }
        return sb.toString();
    }

    private static String compactTime(String raw) {
        String s = String.valueOf(raw == null ? "" : raw).trim();
        if (s.isEmpty()) return "";
        s = s.replace("T", " ").replace("+08:00", "").replace("Z", "");
        if (s.length() >= 16 && s.charAt(4) == '-') {
            return s.substring(5, 16);
        }
        return s.length() > 16 ? s.substring(0, 16) : s;
    }
}
