package com.sumitalk.app;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityService.ScreenshotResult;
import android.accessibilityservice.AccessibilityService.TakeScreenshotCallback;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.util.Base64;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

public class SumiAccessibilityService extends AccessibilityService {
    private static final String TAG = "SumiA11yService";
    private static final String API_BASE = "https://duxy-home.com";
    private static final long REPORT_MIN_INTERVAL_MS = 1500L;
    private static final int MAX_IMAGE_WIDTH = 1080;
    private static volatile SumiAccessibilityService activeInstance;
    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private String lastPackageName = "";
    private long lastReportedAt = 0L;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        activeInstance = this;
    }

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

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (activeInstance == this) activeInstance = null;
        ioExecutor.shutdownNow();
    }

    public static boolean requestScreenshot(String requestId) {
        SumiAccessibilityService svc = activeInstance;
        if (svc == null || requestId == null || requestId.trim().isEmpty()) {
            return false;
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return false;
        }
        svc.captureScreenshotForBridge(requestId.trim());
        return true;
    }

    private void reportForegroundApp(String packageName, String className) {
        ioExecutor.execute(() -> doReportForegroundApp(packageName, className));
    }

    private void doReportForegroundApp(String packageName, String className) {
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

    private void captureScreenshotForBridge(String requestId) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            completeScreenshotError(requestId, "accessibility_screenshot_unsupported");
            return;
        }
        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    ioExecutor,
                    new TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(ScreenshotResult result) {
                            handleScreenshotSuccess(requestId, result);
                        }

                        @Override
                        public void onFailure(int errorCode) {
                            completeScreenshotError(requestId, "accessibility_screenshot_failed_" + errorCode);
                        }
                    });
        } catch (Exception e) {
            completeScreenshotError(requestId, e.getMessage() == null ? String.valueOf(e) : e.getMessage());
        }
    }

    private void handleScreenshotSuccess(String requestId, ScreenshotResult result) {
        HardwareBuffer buffer = null;
        Bitmap hardwareBitmap = null;
        Bitmap bitmap = null;
        try {
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
                throw new IllegalStateException("accessibility_screenshot_unsupported");
            }
            buffer = result.getHardwareBuffer();
            if (buffer == null) throw new IllegalStateException("accessibility_screenshot_buffer_empty");
            hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, result.getColorSpace());
            if (hardwareBitmap == null) throw new IllegalStateException("accessibility_screenshot_bitmap_empty");
            bitmap = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false);
            if (bitmap == null) throw new IllegalStateException("accessibility_screenshot_copy_failed");
            int width = bitmap.getWidth();
            int height = bitmap.getHeight();
            byte[] jpeg = bitmapToJpeg(bitmap);
            JSONObject upload = uploadScreenshot(jpeg, width, height, requestId);
            JSONObject out = new JSONObject();
            out.put("approved", true);
            out.put("capture_source", "accessibility");
            out.put("image_url", upload.optString("image_url", upload.optString("url", "")));
            out.put("url", upload.optString("url", ""));
            out.put("key", upload.optString("key", ""));
            out.put("captured_at", upload.optString("captured_at", nowIso()));
            out.put("width", width);
            out.put("height", height);
            ScreenCaptureBridge.complete(requestId, out);
        } catch (Exception e) {
            completeScreenshotError(requestId, e.getMessage() == null ? String.valueOf(e) : e.getMessage());
        } finally {
            if (bitmap != null) bitmap.recycle();
            if (hardwareBitmap != null) hardwareBitmap.recycle();
            if (buffer != null) buffer.close();
        }
    }

    private byte[] bitmapToJpeg(Bitmap source) throws Exception {
        Bitmap output = source;
        if (source.getWidth() > MAX_IMAGE_WIDTH) {
            int outW = MAX_IMAGE_WIDTH;
            int outH = Math.max(1, Math.round(source.getHeight() * (MAX_IMAGE_WIDTH / (float) source.getWidth())));
            output = Bitmap.createScaledBitmap(source, outW, outH, true);
        }
        ByteArrayOutputStream os = new ByteArrayOutputStream();
        output.compress(Bitmap.CompressFormat.JPEG, 72, os);
        if (output != source) output.recycle();
        return os.toByteArray();
    }

    private JSONObject uploadScreenshot(byte[] jpeg, int width, int height, String requestId) throws Exception {
        SharedPreferences sp = getSharedPreferences(FloatingBallService.PREFS_NAME, MODE_PRIVATE);
        String panelToken = String.valueOf(sp.getString(FloatingBallService.PREF_PANEL_TOKEN, "")).trim();
        String deviceId = String.valueOf(sp.getString(FloatingBallService.PREF_DEVICE_ID, "")).trim();
        if (panelToken.isEmpty() || deviceId.isEmpty()) throw new IllegalStateException("missing_panel_auth");

        JSONObject payload = new JSONObject();
        payload.put("device_id", deviceId);
        payload.put("request_id", requestId);
        payload.put("mime_type", "image/jpeg");
        payload.put("image_base64", Base64.encodeToString(jpeg, Base64.NO_WRAP));
        payload.put("captured_at", nowIso());
        payload.put("width", width);
        payload.put("height", height);

        HttpURLConnection conn = null;
        try {
            URL url = new URL(API_BASE + "/miniapp-api/device-screenshots");
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(15000);
            conn.setReadTimeout(30000);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
            conn.setRequestProperty("Authorization", "Bearer " + panelToken);
            byte[] body = payload.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(body);
            }
            int code = conn.getResponseCode();
            InputStream is = code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream();
            String text = readAllText(is);
            if (code < 200 || code >= 300) throw new IllegalStateException("screenshot_upload_http_" + code + ":" + text);
            return new JSONObject(text);
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private void completeScreenshotError(String requestId, String error) {
        try {
            JSONObject result = new JSONObject();
            result.put("approved", false);
            result.put("stage", "accessibility_screenshot");
            result.put("error", error == null ? "accessibility_screenshot_failed" : error);
            ScreenCaptureBridge.complete(requestId, result);
        } catch (Exception ignored) {
        }
    }

    private String readAllText(InputStream is) throws Exception {
        if (is == null) return "";
        ByteArrayOutputStream os = new ByteArrayOutputStream();
        byte[] buf = new byte[2048];
        int n;
        while ((n = is.read(buf)) > 0) {
            os.write(buf, 0, n);
        }
        return new String(os.toByteArray(), java.nio.charset.StandardCharsets.UTF_8);
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
