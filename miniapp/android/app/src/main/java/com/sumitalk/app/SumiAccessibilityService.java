package com.sumitalk.app;

import android.accessibilityservice.AccessibilityService;
import android.content.SharedPreferences;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import org.json.JSONObject;

public class SumiAccessibilityService extends AccessibilityService {
    private static final String TAG = "SumiA11yService";
    private static final String API_BASE = "https://duxy-home.com";
    private static final long REPORT_MIN_INTERVAL_MS = 1500L;
    private String lastPackageName = "";
    private long lastReportedAt = 0L;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        int type = event.getEventType();
        if (type != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                && type != AccessibilityEvent.TYPE_WINDOWS_CHANGED) {
            return;
        }
        CharSequence pkg = event.getPackageName();
        String packageName = String.valueOf(pkg == null ? "" : pkg).trim();
        if (packageName.isEmpty() || packageName.equals(getPackageName())) return;
        long now = System.currentTimeMillis();
        if (packageName.equals(lastPackageName) && now - lastReportedAt < REPORT_MIN_INTERVAL_MS) {
            return;
        }
        lastPackageName = packageName;
        lastReportedAt = now;
        reportForegroundApp(packageName, String.valueOf(event.getClassName() == null ? "" : event.getClassName()).trim());
    }

    @Override
    public void onInterrupt() {
        // no-op
    }

    private void reportForegroundApp(String packageName, String className) {
        SharedPreferences sp = getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE);
        String panelToken = String.valueOf(sp.getString(FloatingBallService.PREF_PANEL_TOKEN, "")).trim();
        String deviceId = String.valueOf(sp.getString(FloatingBallService.PREF_DEVICE_ID, "")).trim();
        if (panelToken.isEmpty() || deviceId.isEmpty()) return;

        HttpURLConnection conn = null;
        try {
            JSONObject app = new JSONObject();
            app.put("packageName", packageName);
            app.put("appName", resolveAppLabel(packageName));
            if (!className.isEmpty()) app.put("className", className);
            app.put("source", "accessibility");
            app.put("observedAt", nowIso());

            JSONObject payload = new JSONObject();
            payload.put("device_id", deviceId);
            payload.put("app", app);

            URL url = new URL(API_BASE + "/miniapp-api/device-state/foreground-app");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            conn.setRequestProperty("Authorization", "Bearer " + panelToken);
            byte[] body = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(body);
            }
            int code = conn.getResponseCode();
            if (code < 200 || code >= 300) {
                Log.w(TAG, "reportForegroundApp non-2xx code=" + code);
            }
        } catch (Exception e) {
            Log.w(TAG, "reportForegroundApp failed", e);
        } finally {
            if (conn != null) conn.disconnect();
        }
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

    private String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new Date());
    }
}
