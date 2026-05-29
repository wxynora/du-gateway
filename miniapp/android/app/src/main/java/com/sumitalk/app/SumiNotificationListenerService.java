package com.sumitalk.app;

import android.app.Notification;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

public class SumiNotificationListenerService extends NotificationListenerService {
    private static final String TAG = "SumiNotificationListener";
    private static final String API_BASE = "https://duxy-home.com";
    public static final String NOTIFY_FOR_XIAOMI_PACKAGE = "com.mc.xiaomi1";
    public static final String PREF_HEALTH_REPORT_INTERVAL_SECONDS = "health_report_interval_seconds";
    public static final String PREF_HEALTH_REPORT_LOGS_JSON = "health_report_logs_json";
    public static final String PREF_HEALTH_LAST_PAYLOAD_JSON = "health_last_payload_json";
    public static final int DEFAULT_HEALTH_REPORT_INTERVAL_SECONDS = 60;
    public static final int MIN_HEALTH_REPORT_INTERVAL_SECONDS = 15;
    public static final int MAX_HEALTH_REPORT_INTERVAL_SECONDS = 3600;
    private static final int MAX_HEALTH_LOG_ROWS = 80;
    private static final int MAX_RAW_TEXT_CHARS = 500;

    private static final Pattern HEART_RATE_BEFORE_PATTERN =
            Pattern.compile("(\\d{2,3})\\s*(?:脉搏/分|心率|次/分|bpm|pulse|heart\\s*rate|hr\\b)", Pattern.CASE_INSENSITIVE);
    private static final Pattern HEART_RATE_AFTER_PATTERN =
            Pattern.compile("(?:脉搏/分|心率|pulse|heart\\s*rate|hr\\b|bpm)\\D{0,12}(\\d{2,3})", Pattern.CASE_INSENSITIVE);
    private static final Pattern STEPS_BEFORE_PATTERN =
            Pattern.compile("([0-9][0-9,]{0,7})\\s*(?:步数|步|steps?|step\\s*count)", Pattern.CASE_INSENSITIVE);
    private static final Pattern STEPS_AFTER_PATTERN =
            Pattern.compile("(?:步数|steps?|step\\s*count)\\D{0,16}([0-9][0-9,]{0,7})", Pattern.CASE_INSENSITIVE);

    private static volatile SumiNotificationListenerService activeInstance;

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private final Map<String, Long> recentReports = new HashMap<>();

    public static void requestActiveNotificationSnapshot() {
        SumiNotificationListenerService svc = activeInstance;
        if (svc != null) {
            svc.reportActiveNotifyForXiaomiNotifications();
        }
    }

    public static boolean isListenerConnected() {
        return activeInstance != null;
    }

    public static int getHealthReportIntervalSeconds(android.content.Context ctx) {
        if (ctx == null) return DEFAULT_HEALTH_REPORT_INTERVAL_SECONDS;
        int saved =
                ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                        .getInt(PREF_HEALTH_REPORT_INTERVAL_SECONDS, DEFAULT_HEALTH_REPORT_INTERVAL_SECONDS);
        return clampIntervalSeconds(saved);
    }

    public static void setHealthReportIntervalSeconds(android.content.Context ctx, int seconds) {
        if (ctx == null) return;
        ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                .edit()
                .putInt(PREF_HEALTH_REPORT_INTERVAL_SECONDS, clampIntervalSeconds(seconds))
                .apply();
    }

    public static JSONArray getHealthReportLogs(android.content.Context ctx) {
        if (ctx == null) return new JSONArray();
        try {
            String raw =
                    ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                            .getString(PREF_HEALTH_REPORT_LOGS_JSON, "[]");
            JSONArray arr = new JSONArray(String.valueOf(raw == null ? "[]" : raw));
            JSONArray out = new JSONArray();
            int start = Math.max(0, arr.length() - MAX_HEALTH_LOG_ROWS);
            for (int i = start; i < arr.length(); i++) {
                out.put(arr.opt(i));
            }
            return out;
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    public static JSONObject getLastHealthPayload(android.content.Context ctx) {
        if (ctx == null) return new JSONObject();
        try {
            String raw =
                    ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                            .getString(PREF_HEALTH_LAST_PAYLOAD_JSON, "{}");
            JSONObject obj = new JSONObject(String.valueOf(raw == null ? "{}" : raw));
            return obj;
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    private static int clampIntervalSeconds(int seconds) {
        if (seconds < MIN_HEALTH_REPORT_INTERVAL_SECONDS) return MIN_HEALTH_REPORT_INTERVAL_SECONDS;
        if (seconds > MAX_HEALTH_REPORT_INTERVAL_SECONDS) return MAX_HEALTH_REPORT_INTERVAL_SECONDS;
        return seconds;
    }

    @Override
    public void onListenerConnected() {
        super.onListenerConnected();
        activeInstance = this;
        reportActiveNotifyForXiaomiNotifications();
    }

    @Override
    public void onListenerDisconnected() {
        if (activeInstance == this) activeInstance = null;
        super.onListenerDisconnected();
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        handleNotification(sbn);
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (activeInstance == this) activeInstance = null;
        ioExecutor.shutdownNow();
    }

    private void reportActiveNotifyForXiaomiNotifications() {
        ioExecutor.execute(
                () -> {
                    try {
                        StatusBarNotification[] active = getActiveNotifications();
                        if (active == null || active.length <= 0) return;
                        for (StatusBarNotification sbn : active) {
                            handleNotification(sbn);
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "reportActiveNotifyForXiaomiNotifications failed", e);
                    }
                });
    }

    private void handleNotification(StatusBarNotification sbn) {
        if (sbn == null || !isNotifyForXiaomi(sbn)) return;
        JSONObject payload = buildHealthPayload(sbn);
        if (payload == null) {
            appendHealthLog("skip", "Notify 通知里没有解析到心率/步数", null, 0);
            return;
        }
        rememberLastPayload(payload, "observed", 0);
        if (shouldSkipDuplicate(payload)) return;
        postHealth(payload);
    }

    private boolean isNotifyForXiaomi(StatusBarNotification sbn) {
        String pkg = String.valueOf(sbn.getPackageName() == null ? "" : sbn.getPackageName()).trim();
        if (NOTIFY_FOR_XIAOMI_PACKAGE.equals(pkg)) return true;
        String label = resolveAppLabel(pkg).toLowerCase(Locale.US);
        return label.contains("notify for xiaomi");
    }

    private JSONObject buildHealthPayload(StatusBarNotification sbn) {
        try {
            Notification n = sbn.getNotification();
            if (n == null) return null;
            Bundle extras = n.extras;
            String pkg = String.valueOf(sbn.getPackageName() == null ? "" : sbn.getPackageName()).trim();
            String title = textFromExtras(extras, Notification.EXTRA_TITLE);
            String rawText =
                    clip(
                            joinNonEmpty(
                                    title,
                                    textFromExtras(extras, Notification.EXTRA_BIG_TEXT),
                                    textFromExtras(extras, Notification.EXTRA_TEXT),
                                    textFromExtras(extras, Notification.EXTRA_SUMMARY_TEXT),
                                    textFromExtras(extras, Notification.EXTRA_SUB_TEXT),
                                    textLinesFromExtras(extras)),
                            MAX_RAW_TEXT_CHARS);
            if (rawText.isEmpty()) return null;
            Integer heartRate = extractFirstInt(rawText, HEART_RATE_BEFORE_PATTERN, HEART_RATE_AFTER_PATTERN);
            Integer steps = extractFirstInt(rawText, STEPS_BEFORE_PATTERN, STEPS_AFTER_PATTERN);
            if (heartRate == null && steps == null) return null;
            JSONObject payload = new JSONObject();
            payload.put("packageName", pkg);
            payload.put("appName", resolveAppLabel(pkg));
            payload.put("raw_text", rawText);
            payload.put("source", "sumitalk_notify_for_xiaomi");
            payload.put("captured_at", nowIso());
            payload.put("posted_at", sbn.getPostTime() > 0L ? isoFromMillis(sbn.getPostTime()) : nowIso());
            if (heartRate != null) payload.put("heart_rate", heartRate);
            if (steps != null) payload.put("steps", steps);
            return payload;
        } catch (Exception e) {
            Log.w(TAG, "buildHealthPayload failed", e);
            return null;
        }
    }

    private Integer extractFirstInt(String text, Pattern... patterns) {
        String src = String.valueOf(text == null ? "" : text);
        for (Pattern pattern : patterns) {
            Matcher matcher = pattern.matcher(src);
            if (!matcher.find()) continue;
            try {
                return Integer.parseInt(matcher.group(1).replace(",", ""));
            } catch (Exception e) {
                return null;
            }
        }
        return null;
    }

    private boolean shouldSkipDuplicate(JSONObject payload) {
        String fingerprint =
                String.valueOf(payload.optString("heart_rate", "")).trim()
                        + "|"
                        + String.valueOf(payload.optString("steps", "")).trim()
                        + "|"
                        + String.valueOf(payload.optString("raw_text", "")).trim();
        long now = System.currentTimeMillis();
        synchronized (recentReports) {
            Long last = recentReports.get(fingerprint);
            long intervalMs = getHealthReportIntervalSeconds(this) * 1000L;
            if (last != null && now - last < intervalMs) {
                appendHealthLog("skip", "同一内容在上报间隔内跳过", payload, 0);
                return true;
            }
            recentReports.put(fingerprint, now);
            if (recentReports.size() > 40) {
                recentReports.clear();
                recentReports.put(fingerprint, now);
            }
            return false;
        }
    }

    private void postHealth(JSONObject payload) {
        ioExecutor.execute(
                () -> {
                    try {
                        SharedPreferences sp = getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE);
                        String token = String.valueOf(sp.getString(FloatingBallService.PREF_PANEL_TOKEN, "")).trim();
                        String deviceId = String.valueOf(sp.getString(FloatingBallService.PREF_DEVICE_ID, "")).trim();
                        if (token.isEmpty() || deviceId.isEmpty()) {
                            appendHealthLog("error", "缺少登录 token 或设备 ID，未上报", payload, 0);
                            rememberLastPayload(payload, "missing_auth", 0);
                            return;
                        }
                        payload.put("device_id", deviceId);
                        payload.put("deviceId", deviceId);
                        int code = postJson(token, payload);
                        if (code >= 200 && code < 300) {
                            appendHealthLog("ok", "已上报健康数据", payload, code);
                            rememberLastPayload(payload, "uploaded", code);
                        } else {
                            appendHealthLog("error", "健康数据上报失败 HTTP " + code, payload, code);
                            rememberLastPayload(payload, "http_error", code);
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "postHealth failed", e);
                        appendHealthLog("error", "健康数据上报异常：" + e.getClass().getSimpleName(), payload, 0);
                        rememberLastPayload(payload, "exception", 0);
                    }
                });
    }

    private int postJson(String token, JSONObject payload) throws Exception {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(API_BASE + "/miniapp-api/device-state/health");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            conn.setRequestProperty("Authorization", "Bearer " + token);
            byte[] body = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(body);
            }
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                Log.w(TAG, "post health non-2xx code=" + code);
            }
            return code;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private String textFromExtras(Bundle extras, String key) {
        if (extras == null || key == null) return "";
        CharSequence value = extras.getCharSequence(key);
        return value == null ? "" : String.valueOf(value).trim();
    }

    private String joinNonEmpty(String... values) {
        StringBuilder sb = new StringBuilder();
        for (String value : values) {
            String text = String.valueOf(value == null ? "" : value).trim();
            if (text.isEmpty()) continue;
            if (sb.length() > 0) sb.append(" ");
            sb.append(text);
        }
        return sb.toString().replaceAll("\\s+", " ").trim();
    }

    private String textLinesFromExtras(Bundle extras) {
        if (extras == null) return "";
        CharSequence[] lines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        if (lines == null || lines.length <= 0) return "";
        StringBuilder sb = new StringBuilder();
        for (CharSequence line : lines) {
            String text = String.valueOf(line == null ? "" : line).trim();
            if (text.isEmpty()) continue;
            if (sb.length() > 0) sb.append(" ");
            sb.append(text);
        }
        return sb.toString();
    }

    private String clip(String value, int maxChars) {
        String text = String.valueOf(value == null ? "" : value).replaceAll("\\s+", " ").trim();
        int max = Math.max(1, maxChars);
        if (text.length() <= max) return text;
        return text.substring(0, Math.max(1, max - 1)).trim() + "...";
    }

    private String resolveAppLabel(String packageName) {
        try {
            android.content.pm.ApplicationInfo info = getPackageManager().getApplicationInfo(packageName, 0);
            CharSequence label = getPackageManager().getApplicationLabel(info);
            String text = String.valueOf(label == null ? "" : label).trim();
            return text.isEmpty() ? packageName : text;
        } catch (Exception e) {
            return packageName;
        }
    }

    private void rememberLastPayload(JSONObject payload, String status, int code) {
        try {
            JSONObject obj = new JSONObject(payload == null ? "{}" : payload.toString());
            obj.put("status", status);
            if (code > 0) obj.put("http_code", code);
            obj.put("status_at", nowIso());
            getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(PREF_HEALTH_LAST_PAYLOAD_JSON, obj.toString())
                    .apply();
        } catch (Exception ignored) {
        }
    }

    private void appendHealthLog(String level, String message, JSONObject payload, int code) {
        appendHealthLog(this, level, message, payload, code);
    }

    private static void appendHealthLog(android.content.Context ctx, String level, String message, JSONObject payload, int code) {
        if (ctx == null) return;
        synchronized (SumiNotificationListenerService.class) {
            try {
                SharedPreferences sp = ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE);
                JSONArray existing = new JSONArray(String.valueOf(sp.getString(PREF_HEALTH_REPORT_LOGS_JSON, "[]")));
                JSONArray next = new JSONArray();
                int start = Math.max(0, existing.length() - MAX_HEALTH_LOG_ROWS + 1);
                for (int i = start; i < existing.length(); i++) {
                    next.put(existing.opt(i));
                }
                JSONObject row = new JSONObject();
                row.put("at", isoFromMillisStatic(System.currentTimeMillis()));
                row.put("level", String.valueOf(level == null ? "" : level).trim());
                row.put("message", String.valueOf(message == null ? "" : message).trim());
                if (code > 0) row.put("http_code", code);
                if (payload != null) {
                    if (payload.has("heart_rate")) row.put("heart_rate", payload.optInt("heart_rate"));
                    if (payload.has("steps")) row.put("steps", payload.optInt("steps"));
                    String raw = String.valueOf(payload.optString("raw_text", "")).trim();
                    if (!raw.isEmpty()) row.put("raw_text", raw.length() > 180 ? raw.substring(0, 179).trim() + "..." : raw);
                }
                next.put(row);
                sp.edit().putString(PREF_HEALTH_REPORT_LOGS_JSON, next.toString()).apply();
            } catch (Exception ignored) {
            }
        }
    }

    private String nowIso() {
        return isoFromMillis(System.currentTimeMillis());
    }

    private String isoFromMillis(long millis) {
        return isoFromMillisStatic(millis);
    }

    private static String isoFromMillisStatic(long millis) {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date(millis));
    }
}
