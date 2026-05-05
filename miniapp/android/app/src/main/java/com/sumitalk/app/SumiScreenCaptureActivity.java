package com.sumitalk.app;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.DisplayMetrics;
import android.util.Log;
import android.view.WindowManager;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.text.SimpleDateFormat;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;

public class SumiScreenCaptureActivity extends Activity {
    private static final String TAG = "SumiScreenCapture";
    private static final int REQ_SCREEN_CAPTURE = 4108;
    private static final int MAX_IMAGE_WIDTH = 1080;

    private String requestId = "";
    private String panelToken = "";
    private String panelDeviceId = "";
    private String apiBase = "https://duxy-home.com";
    private MediaProjectionManager projectionManager;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Intent intent = getIntent();
        requestId = extra(intent, "request_id");
        panelToken = extra(intent, "panel_token");
        panelDeviceId = extra(intent, "device_id");
        String base = extra(intent, "api_base");
        if (!base.isEmpty()) apiBase = base;
        projectionManager = (MediaProjectionManager) getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        if (projectionManager == null || requestId.isEmpty() || panelToken.isEmpty()) {
            completeError("screen_capture_init_failed");
            finish();
            return;
        }
        startActivityForResult(projectionManager.createScreenCaptureIntent(), REQ_SCREEN_CAPTURE);
    }

    private String extra(Intent intent, String key) {
        if (intent == null) return "";
        String value = intent.getStringExtra(key);
        return value == null ? "" : value.trim();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_SCREEN_CAPTURE) {
            completeError("unknown_request");
            finish();
            return;
        }
        if (resultCode != RESULT_OK || data == null) {
            completeDeclined();
            finish();
            return;
        }
        new Thread(() -> captureAndUpload(resultCode, data), "SumiScreenCaptureUpload").start();
    }

    private void captureAndUpload(int resultCode, Intent data) {
        MediaProjection projection = null;
        ImageReader reader = null;
        VirtualDisplay display = null;
        try {
            projection = projectionManager.getMediaProjection(resultCode, data);
            if (projection == null) throw new IllegalStateException("media_projection_unavailable");
            projection.registerCallback(
                    new MediaProjection.Callback() {
                        @Override
                        public void onStop() {
                        }
                    },
                    new Handler(Looper.getMainLooper()));

            DisplayMetrics metrics = new DisplayMetrics();
            WindowManager wm = (WindowManager) getSystemService(WINDOW_SERVICE);
            if (wm == null) throw new IllegalStateException("window_manager_unavailable");
            wm.getDefaultDisplay().getRealMetrics(metrics);
            int width = Math.max(1, metrics.widthPixels);
            int height = Math.max(1, metrics.heightPixels);
            int density = Math.max(1, metrics.densityDpi);

            reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
            CountDownLatch latch = new CountDownLatch(1);
            AtomicReference<Image> imageRef = new AtomicReference<>();
            reader.setOnImageAvailableListener(
                    r -> {
                        Image img = r.acquireLatestImage();
                        if (img != null && imageRef.compareAndSet(null, img)) {
                            latch.countDown();
                        } else if (img != null) {
                            img.close();
                        }
                    },
                    new Handler(Looper.getMainLooper()));

            display =
                    projection.createVirtualDisplay(
                            "sumitalk-screen-check",
                            width,
                            height,
                            density,
                            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                            reader.getSurface(),
                            null,
                            null);

            latch.await(2500L, TimeUnit.MILLISECONDS);
            Image image = imageRef.get();
            if (image == null) {
                image = reader.acquireLatestImage();
            }
            if (image == null) throw new IllegalStateException("screen_image_unavailable");

            byte[] jpeg = imageToJpeg(image, width, height);
            image.close();
            JSONObject upload = uploadScreenshot(jpeg, width, height);
            JSONObject result = new JSONObject();
            result.put("approved", true);
            result.put("image_url", upload.optString("image_url", upload.optString("url", "")));
            result.put("url", upload.optString("url", ""));
            result.put("key", upload.optString("key", ""));
            result.put("captured_at", upload.optString("captured_at", nowIso()));
            result.put("width", width);
            result.put("height", height);
            ScreenCaptureBridge.complete(requestId, result);
        } catch (Exception e) {
            Log.w(TAG, "captureAndUpload failed", e);
            completeError(e.getMessage() == null ? String.valueOf(e) : e.getMessage());
        } finally {
            if (display != null) display.release();
            if (reader != null) reader.close();
            if (projection != null) projection.stop();
            runOnUiThread(this::finish);
        }
    }

    private byte[] imageToJpeg(Image image, int width, int height) throws Exception {
        Image.Plane[] planes = image.getPlanes();
        if (planes == null || planes.length <= 0) throw new IllegalStateException("screen_image_plane_empty");
        ByteBuffer buffer = planes[0].getBuffer();
        int pixelStride = planes[0].getPixelStride();
        int rowStride = planes[0].getRowStride();
        int rowPadding = rowStride - pixelStride * width;
        Bitmap bitmap = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888);
        bitmap.copyPixelsFromBuffer(buffer);
        Bitmap cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height);
        bitmap.recycle();

        Bitmap output = cropped;
        if (width > MAX_IMAGE_WIDTH) {
            int outW = MAX_IMAGE_WIDTH;
            int outH = Math.max(1, Math.round(height * (MAX_IMAGE_WIDTH / (float) width)));
            output = Bitmap.createScaledBitmap(cropped, outW, outH, true);
            cropped.recycle();
        }
        ByteArrayOutputStream os = new ByteArrayOutputStream();
        output.compress(Bitmap.CompressFormat.JPEG, 72, os);
        if (output != cropped) output.recycle();
        return os.toByteArray();
    }

    private JSONObject uploadScreenshot(byte[] jpeg, int width, int height) throws Exception {
        JSONObject payload = new JSONObject();
        payload.put("device_id", panelDeviceId);
        payload.put("request_id", requestId);
        payload.put("mime_type", "image/jpeg");
        payload.put("image_base64", Base64.encodeToString(jpeg, Base64.NO_WRAP));
        payload.put("captured_at", nowIso());
        payload.put("width", width);
        payload.put("height", height);

        HttpURLConnection conn = null;
        try {
            URL url = new URL(apiBase.replaceAll("/+$", "") + "/miniapp-api/device-screenshots");
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

    private void completeDeclined() {
        try {
            JSONObject result = new JSONObject();
            result.put("approved", false);
            result.put("reason", "system_permission_denied");
            ScreenCaptureBridge.complete(requestId, result);
        } catch (Exception ignored) {
        }
    }

    private void completeError(String error) {
        try {
            JSONObject result = new JSONObject();
            result.put("approved", false);
            result.put("error", error == null ? "screen_capture_failed" : error);
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

    private String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date());
    }
}
