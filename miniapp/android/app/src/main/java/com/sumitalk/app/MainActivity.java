package com.sumitalk.app;

import android.Manifest;
import android.app.AppOpsManager;
import android.app.AlarmManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.webkit.WebSettings;
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
    private static final int REQ_RUNTIME_PERMS = 1201;
    private static final String TAG = "SumiTalkMain";
    private static final String API_BASE = "https://duxy-home.com";
    private boolean specialPermissionFlowStarted = false;
    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private String panelToken = "";
    private String panelDeviceId = "";
    private boolean panelStateSynced = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestRuntimePermissionsIfNeeded();
        ensureSpecialPermissions();
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        WebSettings settings = getBridge().getWebView().getSettings();
        if (settings != null) {
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        }
        getBridge().getWebView().clearCache(true);
        getBridge().getWebView().loadUrl("https://duxy-home.com/miniapp?ts=" + System.currentTimeMillis());
        syncPanelStateFromWebView();
    }

    @Override
    public void onResume() {
        super.onResume();
        if (specialPermissionFlowStarted) {
            ensureSpecialPermissions();
        }
        syncPanelStateFromWebView();
        reportUsageStatsSnapshot();
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        ioExecutor.shutdownNow();
    }

    private void requestRuntimePermissionsIfNeeded() {
        List<String> needs = new ArrayList<>();

        addIfMissing(needs, Manifest.permission.RECORD_AUDIO);
        addIfMissing(needs, Manifest.permission.CAMERA);

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

    private void syncPanelStateFromWebView() {
        if (getBridge() == null || getBridge().getWebView() == null) {
            return;
        }
        getBridge()
                .getWebView()
                .post(
                        () ->
                                getBridge()
                                        .getWebView()
                                        .evaluateJavascript(
                                                "(function(){try{return JSON.stringify({panelToken:localStorage.getItem('miniapp.panel.token.v1')||'',deviceId:localStorage.getItem('miniapp.panel.device-id.v1')||''});}catch(e){return JSON.stringify({panelToken:'',deviceId:''});}})();",
                                                value -> {
                                                    try {
                                                        String raw = String.valueOf(value == null ? "" : value).trim();
                                                        if (raw.startsWith("\"") && raw.endsWith("\"")) {
                                                            raw = new org.json.JSONTokener(raw).nextValue().toString();
                                                        }
                                                        JSONObject obj = new JSONObject(raw);
                                                        panelToken = String.valueOf(obj.optString("panelToken", "")).trim();
                                                        panelDeviceId = String.valueOf(obj.optString("deviceId", "")).trim();
                                                        savePanelState();
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
        if (panelToken.isEmpty() || !hasUsageStatsPermission()) return;
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
                            item.put("packageName", String.valueOf(stat.getPackageName()));
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

    private String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date());
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
