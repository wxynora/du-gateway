package com.sumitalk.app;

import android.Manifest;
import android.app.AppOpsManager;
import android.app.AlarmManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import com.getcapacitor.BridgeActivity;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

public class MainActivity extends BridgeActivity {
    public static final String ACTION_OPEN_VOICE_CALL = "com.sumitalk.app.action.OPEN_VOICE_CALL";
    public static final String ACTION_OPEN_VOICE_WAKE = "com.sumitalk.app.action.OPEN_VOICE_WAKE";
    public static final String EXTRA_VOICE_CALL_INVITE_JSON = "voice_call_invite_json";
    private static final int REQ_RUNTIME_PERMS = 1201;
    private static final String TAG = "SumiTalkMain";
    private static final String API_BASE = "https://duxy-home.com";
    private static final String PREF_NATIVE_DEVICE = "native_device_id";
    private static final String PANEL_DEVICE_ID_STORAGE_KEY = "miniapp.panel.device-id.v1";
    private static final String PANEL_PREVIOUS_DEVICE_ID_STORAGE_KEY = "miniapp.panel.device-id.previous.v1";
    private boolean specialPermissionFlowStarted = false;
    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private String panelToken = "";
    private String panelDeviceId = "";
    private boolean panelStateSynced = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(OverlayControlPlugin.class);
        super.onCreate(savedInstanceState);
        applyLockScreenPresentation(getIntent());
        requestRuntimePermissionsIfNeeded();
        ensureSpecialPermissions();
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebView webView = getBridge().getWebView();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.KITKAT) {
            WebView.setWebContentsDebuggingEnabled(true);
        }
        webView.addJavascriptInterface(new ClientLogBridge(), "SumiNativeLog");
        webView.clearCache(true);
        WebSettings settings = webView.getSettings();
        if (settings != null) {
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
            settings.setDomStorageEnabled(true);
            settings.setDatabaseEnabled(true);
            settings.setJavaScriptEnabled(true);
            settings.setJavaScriptCanOpenWindowsAutomatically(true);
            settings.setMediaPlaybackRequiresUserGesture(false);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
            }
        }
        schedulePanelStateSyncRetries();
        syncPanelStateFromWebView();
        handleVoiceCallIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        applyLockScreenPresentation(intent);
        handleVoiceCallIntent(intent);
    }

    private static class ClientLogBridge {
        @JavascriptInterface
        public void report(String level, String message, String stack) {
            Log.w(
                    TAG,
                    "webview_client_log level="
                            + String.valueOf(level)
                            + " message="
                            + String.valueOf(message)
                            + " stack="
                            + String.valueOf(stack));
        }
    }

    @Override
    public void onResume() {
        super.onResume();
        setAppVisibleFlag(true);
        if (specialPermissionFlowStarted) {
            ensureSpecialPermissions();
        }
        syncPanelStateFromWebView();
        reportUsageStatsSnapshot();
    }

    @Override
    public void onPause() {
        super.onPause();
        applyLockScreenPresentation(null);
        setAppVisibleFlag(false);
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        mainHandler.removeCallbacksAndMessages(null);
        ioExecutor.shutdownNow();
    }

    private void handleVoiceCallIntent(Intent intent) {
        if (intent == null) return;
        String inviteJson = String.valueOf(intent.getStringExtra(EXTRA_VOICE_CALL_INVITE_JSON) == null ? "" : intent.getStringExtra(EXTRA_VOICE_CALL_INVITE_JSON)).trim();
        boolean voiceWake = ACTION_OPEN_VOICE_WAKE.equals(intent.getAction());
        boolean voiceCall = ACTION_OPEN_VOICE_CALL.equals(intent.getAction());
        if (inviteJson.isEmpty() && (voiceCall || voiceWake)) {
            try {
                JSONObject fallback = new JSONObject();
                fallback.put("callId", (voiceWake ? "wake_" : "call_") + System.currentTimeMillis());
                fallback.put("callerName", "渡");
                fallback.put("title", voiceWake ? "叫渡" : "渡来电");
                fallback.put("openingLine", "");
                if (voiceWake) {
                    fallback.put("reason", "lockscreen_voice_wake");
                    fallback.put("autoStartRecording", true);
                    fallback.put("source", "voice_wake_intent");
                }
                inviteJson = fallback.toString();
            } catch (Exception ignored) {
            }
        }
        if (inviteJson.isEmpty()) return;
        final String payload = inviteJson;
        mainHandler.postDelayed(() -> dispatchVoiceCallInviteToWebView(payload), 260);
        mainHandler.postDelayed(() -> dispatchVoiceCallInviteToWebView(payload), 1200);
    }

    private void dispatchVoiceCallInviteToWebView(String inviteJson) {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebView webView = getBridge().getWebView();
        String quoted = JSONObject.quote(inviteJson == null ? "" : inviteJson);
        String script =
                "(function(){"
                        + "try{"
                        + "var detail=JSON.parse(" + quoted + ");"
                        + "localStorage.setItem('miniapp.voiceCall.pendingInvite', JSON.stringify(detail));"
                        + "window.dispatchEvent(new CustomEvent('sumitalk-voice-call-invite',{detail:detail}));"
                        + "}catch(e){console.error('voice call invite dispatch failed',e);}"
                        + "})();";
        webView.evaluateJavascript(script, null);
    }

    private boolean isVoiceLaunchIntent(Intent intent) {
        if (intent == null) return false;
        String action = String.valueOf(intent.getAction() == null ? "" : intent.getAction());
        if (ACTION_OPEN_VOICE_CALL.equals(action) || ACTION_OPEN_VOICE_WAKE.equals(action)) return true;
        return String.valueOf(intent.getStringExtra(EXTRA_VOICE_CALL_INVITE_JSON) == null ? "" : intent.getStringExtra(EXTRA_VOICE_CALL_INVITE_JSON)).trim().length() > 0;
    }

    private void applyLockScreenPresentation(Intent intent) {
        boolean enabled = isVoiceLaunchIntent(intent);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(enabled);
            setTurnScreenOn(enabled);
        } else if (enabled) {
            getWindow().addFlags(
                    WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                            | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                            | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } else {
            getWindow().clearFlags(
                    WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
                            | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
                            | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }

    private void requestRuntimePermissionsIfNeeded() {
        List<String> needs = new ArrayList<>();

        addIfMissing(needs, Manifest.permission.RECORD_AUDIO);
        addIfMissing(needs, Manifest.permission.CAMERA);
        addIfMissing(needs, Manifest.permission.ACCESS_FINE_LOCATION);
        addIfMissing(needs, Manifest.permission.ACCESS_COARSE_LOCATION);
        addIfMissing(needs, Manifest.permission.READ_CALENDAR);
        addIfMissing(needs, Manifest.permission.WRITE_CALENDAR);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            addIfMissing(needs, Manifest.permission.POST_NOTIFICATIONS);
            addIfMissing(needs, Manifest.permission.READ_MEDIA_IMAGES);
            addIfMissing(needs, Manifest.permission.READ_MEDIA_VIDEO);
            addIfMissing(needs, Manifest.permission.READ_MEDIA_AUDIO);
        } else {
            addIfMissing(needs, Manifest.permission.READ_EXTERNAL_STORAGE);
        }

        if (!needs.isEmpty()) {
            ActivityCompat.requestPermissions(this, needs.toArray(new String[0]), REQ_RUNTIME_PERMS);
        }
    }

    private void addIfMissing(List<String> out, String perm) {
        if (ContextCompat.checkSelfPermission(this, perm) != PackageManager.PERMISSION_GRANTED) {
            out.add(perm);
        }
    }

    private void ensureSpecialPermissions() {
        // Overlay permission
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            specialPermissionFlowStarted = true;
            Intent i = new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName()));
            startActivity(i);
            return;
        }

        // Exact alarm permission (Android 12+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            AlarmManager am = getSystemService(AlarmManager.class);
            if (am != null && !am.canScheduleExactAlarms()) {
                specialPermissionFlowStarted = true;
                Intent i = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + getPackageName()));
                startActivity(i);
                return;
            }
        }

        // Ignore battery optimization
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                specialPermissionFlowStarted = true;
                Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()));
                startActivity(i);
                return;
            }
        }

        // Usage stats access
        if (!hasUsageStatsPermission()) {
            specialPermissionFlowStarted = true;
            Intent i = new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS);
            startActivity(i);
            return;
        }

        // Notification access is a special settings permission, not a runtime permission.
        if (!isNotificationListenerEnabled()) {
            specialPermissionFlowStarted = true;
            Intent i = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
            startActivity(i);
            return;
        }

        if (!isAccessibilityServiceEnabled()) {
            specialPermissionFlowStarted = true;
            Intent i = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            startActivity(i);
            return;
        }

        specialPermissionFlowStarted = false;
    }

    private boolean hasUsageStatsPermission() {
        AppOpsManager appOps = (AppOpsManager) getSystemService(Context.APP_OPS_SERVICE);
        if (appOps == null) return false;
        int mode;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            mode = appOps.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), getPackageName());
        } else {
            mode = appOps.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), getPackageName());
        }
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    private boolean isNotificationListenerEnabled() {
        try {
            String enabled = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
            if (enabled == null || enabled.trim().isEmpty()) return false;
            ComponentName target = new ComponentName(this, SumiNotificationListenerService.class);
            String targetPackage = getPackageName();
            String targetClass = target.getClassName();
            for (String item : enabled.split(":")) {
                ComponentName component = ComponentName.unflattenFromString(item);
                if (component == null) continue;
                if (targetPackage.equals(component.getPackageName()) && targetClass.equals(component.getClassName())) {
                    return true;
                }
            }
            String lower = enabled.toLowerCase(Locale.US);
            return lower.contains(target.flattenToString().toLowerCase(Locale.US))
                    || lower.contains(target.flattenToShortString().toLowerCase(Locale.US));
        } catch (Exception e) {
            return false;
        }
    }

    private boolean isAccessibilityServiceEnabled() {
        try {
            String enabled = Settings.Secure.getString(getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            String needle = (getPackageName() + "/").toLowerCase(Locale.US);
            return enabled != null && enabled.toLowerCase(Locale.US).contains(needle);
        } catch (Exception e) {
            return false;
        }
    }

    private void syncPanelStateFromWebView() {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        final String stableDeviceId = resolveStableDeviceId();
        final String stableDeviceIdJs = JSONObject.quote(stableDeviceId);
        getBridge()
                .getWebView()
                .post(
                        () ->
                                getBridge()
                                        .getWebView()
                                        .evaluateJavascript(
                                                "(function(){try{var tokenKey='miniapp.panel.token.v1';var deviceKey='"
                                                        + PANEL_DEVICE_ID_STORAGE_KEY
                                                        + "';var prevKey='"
                                                        + PANEL_PREVIOUS_DEVICE_ID_STORAGE_KEY
                                                        + "';var next="
                                                        + stableDeviceIdJs
                                                        + ";var old=(localStorage.getItem(deviceKey)||'').trim();if(next){if(old&&old!==next){var prev=(localStorage.getItem(prevKey)||'').trim();if(!prev||prev===old){localStorage.setItem(prevKey, old);}}localStorage.setItem(deviceKey, next);}return JSON.stringify({panelToken:localStorage.getItem(tokenKey)||'',deviceId:localStorage.getItem(deviceKey)||''});}catch(e){return JSON.stringify({panelToken:'',deviceId:'"
                                                        + stableDeviceId
                                                        + "'});}})();",
                                                value -> {
                                                    try {
                                                        String raw = String.valueOf(value == null ? "" : value).trim();
                                                        if (raw.startsWith("\"") && raw.endsWith("\"")) {
                                                            raw = new org.json.JSONTokener(raw).nextValue().toString();
                                                        }
                                                        JSONObject obj = new JSONObject(raw);
                                                        panelToken = String.valueOf(obj.optString("panelToken", "")).trim();
                                                        panelDeviceId = String.valueOf(obj.optString("deviceId", "")).trim();
                                                        if (panelDeviceId.isEmpty()) {
                                                            panelDeviceId = stableDeviceId;
                                                        }
                                                        savePanelState();
                                                        SumiNotificationListenerService.requestActiveNotificationSnapshot();
                                                        startOrUpdateForegroundOverlayService();
                                                        if (!panelStateSynced && !panelToken.isEmpty()) {
                                                            panelStateSynced = true;
                                                            reportUsageStatsSnapshot();
                                                        }
                                                    } catch (Exception e) {
                                                        Log.w(TAG, "syncPanelStateFromWebView parse failed", e);
                                                    }
                                                }));
    }

    private void reportUsageStatsSnapshot() {
        if (!FloatingBallService.isSenseReportingEnabled(this) || panelToken.isEmpty() || !hasUsageStatsPermission()) return;
        ioExecutor.execute(
                () -> {
                    try {
                        UsageStatsManager usm = (UsageStatsManager) getSystemService(Context.USAGE_STATS_SERVICE);
                        if (usm == null) return;
                        long now = System.currentTimeMillis();
                        long since = now - 24L * 60L * 60L * 1000L;
                        List<UsageStats> stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, since, now);
                        if (stats == null) stats = Collections.emptyList();
                        stats.sort(Comparator.comparingLong(UsageStats::getTotalTimeInForeground).reversed());
                        JSONArray apps = new JSONArray();
                        int count = 0;
                        for (UsageStats stat : stats) {
                            if (stat == null) continue;
                            long ms = stat.getTotalTimeInForeground();
                            if (ms <= 0) continue;
                            JSONObject item = new JSONObject();
                            String packageName = String.valueOf(stat.getPackageName());
                            item.put("packageName", packageName);
                            item.put("appName", resolveAppLabel(packageName));
                            item.put("foregroundMs", ms);
                            item.put("lastTimeUsed", stat.getLastTimeUsed());
                            apps.put(item);
                            count += 1;
                            if (count >= 20) break;
                        }
                        JSONObject payload = new JSONObject();
                        payload.put("device_id", panelDeviceId);
                        payload.put("range", "24h");
                        payload.put("captured_at", nowIso());
                        payload.put("apps", apps);
                        postJson("/miniapp-api/device-state/usage-stats", payload);
                    } catch (Exception e) {
                        Log.w(TAG, "reportUsageStatsSnapshot failed", e);
                    }
                });
    }

    public void requestUsageStatsSnapshot() {
        reportUsageStatsSnapshot();
    }

    private void postJson(String path, JSONObject payload) throws Exception {
        HttpURLConnection conn = null;
        try {
            URL url = new URL(API_BASE + path);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            conn.setRequestProperty("Authorization", "Bearer " + panelToken);
            byte[] body = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(body);
            }
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                Log.w(TAG, "postJson non-2xx " + path + " code=" + code);
            }
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private void schedulePanelStateSyncRetries() {
        long[] delays = new long[] {400L, 1200L, 2800L};
        for (long delay : delays) {
            mainHandler.postDelayed(this::syncPanelStateFromWebView, delay);
        }
    }

    private String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date());
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

    private String resolveStableDeviceId() {
        try {
            String androidId =
                    String.valueOf(Settings.Secure.getString(getContentResolver(), Settings.Secure.ANDROID_ID)).trim();
            if (!androidId.isEmpty() && !"9774d56d682e549c".equals(androidId)) {
                return "android_" + androidId.toLowerCase();
            }
        } catch (Exception ignored) {
        }

        SharedPreferences sp = getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE);
        String existing = String.valueOf(sp.getString(PREF_NATIVE_DEVICE, "")).trim();
        if (!existing.isEmpty()) {
            return existing;
        }
        String next = "native_" + java.util.UUID.randomUUID().toString().replace("-", "");
        sp.edit().putString(PREF_NATIVE_DEVICE, next).apply();
        return next;
    }

    private void savePanelState() {
        try {
            getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putString(FloatingBallService.PREF_PANEL_TOKEN, panelToken)
                    .putString(FloatingBallService.PREF_DEVICE_ID, panelDeviceId)
                    .apply();
        } catch (Exception e) {
            Log.w(TAG, "savePanelState failed", e);
        }
    }

    private void setAppVisibleFlag(boolean visible) {
        try {
            getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE)
                    .edit()
                    .putBoolean(FloatingBallService.PREF_APP_VISIBLE, visible)
                    .apply();
        } catch (Exception e) {
            Log.w(TAG, "setAppVisibleFlag failed", e);
        }
    }

    private void startOrUpdateForegroundOverlayService() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            return;
        }
        Intent intent = new Intent(this, FloatingBallService.class);
        intent.setAction(FloatingBallService.ACTION_START_OR_UPDATE);
        intent.putExtra(FloatingBallService.EXTRA_PANEL_TOKEN, panelToken);
        intent.putExtra(FloatingBallService.EXTRA_DEVICE_ID, panelDeviceId);
        ContextCompat.startForegroundService(this, intent);
    }
}
