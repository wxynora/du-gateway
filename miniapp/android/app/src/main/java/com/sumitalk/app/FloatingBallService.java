package com.sumitalk.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.PixelFormat;
import android.graphics.Point;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.util.DisplayMetrics;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewOutlineProvider;
import android.view.WindowManager;
import android.widget.ImageView;
import androidx.core.app.NotificationCompat;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONObject;

public class FloatingBallService extends Service {
    public static final String ACTION_START_OR_UPDATE = "com.sumitalk.app.action.START_OR_UPDATE";
    public static final String ACTION_STOP = "com.sumitalk.app.action.STOP";
    public static final String EXTRA_PANEL_TOKEN = "panel_token";
    public static final String EXTRA_DEVICE_ID = "device_id";
    public static final String PREFS_NAME = "sumitalk_native_state";
    public static final String PREF_PANEL_TOKEN = "panel_token";
    public static final String PREF_DEVICE_ID = "device_id";
    public static final String PREF_OVERLAY_X = "overlay_x";
    public static final String PREF_OVERLAY_Y = "overlay_y";
    /** User preference: show floating ball (does not revoke overlay permission). */
    public static final String PREF_OVERLAY_VISIBLE = "overlay_visible";

    private static final String TAG = "SumiTalkOverlay";
    private static final String API_BASE = "https://duxy-home.com";
    private static final String CHANNEL_ID = "sumitalk_overlay";
    private static final int NOTIFICATION_ID = 2001;

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private WindowManager windowManager;
    private ImageView overlayView;
    private WindowManager.LayoutParams overlayParams;
    private BroadcastReceiver screenStateReceiver;
    private BroadcastReceiver configChangeReceiver;
    private SharedPreferences prefs;
    private String panelToken = "";
    private String panelDeviceId = "";

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        restorePanelState();
        createNotificationChannel();
        startForeground(NOTIFICATION_ID, buildNotification());
        registerScreenStateReceiver();
        registerConfigChangeReceiver();
        applyOverlayVisibility();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? String.valueOf(intent.getAction()) : "";
        if (ACTION_STOP.equals(action)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        updatePanelState(intent);
        applyOverlayVisibility();
        reportScreenState("app_active");
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        removeOverlay();
        if (screenStateReceiver != null) {
            try {
                unregisterReceiver(screenStateReceiver);
            } catch (Exception ignored) {
            }
            screenStateReceiver = null;
        }
        if (configChangeReceiver != null) {
            try {
                unregisterReceiver(configChangeReceiver);
            } catch (Exception ignored) {
            }
            configChangeReceiver = null;
        }
        ioExecutor.shutdownNow();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void restorePanelState() {
        panelToken = String.valueOf(prefs.getString(PREF_PANEL_TOKEN, "")).trim();
        panelDeviceId = String.valueOf(prefs.getString(PREF_DEVICE_ID, "")).trim();
    }

    private void updatePanelState(Intent intent) {
        if (intent == null) return;
        String nextToken = String.valueOf(intent.getStringExtra(EXTRA_PANEL_TOKEN)).trim();
        String nextDeviceId = String.valueOf(intent.getStringExtra(EXTRA_DEVICE_ID)).trim();
        if (!nextToken.isEmpty()) panelToken = nextToken;
        if (!nextDeviceId.isEmpty()) panelDeviceId = nextDeviceId;
        prefs.edit().putString(PREF_PANEL_TOKEN, panelToken).putString(PREF_DEVICE_ID, panelDeviceId).apply();
    }

    private Notification buildNotification() {
        Intent openIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (openIntent == null) {
            openIntent = new Intent(this, MainActivity.class);
        }
        openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi =
                PendingIntent.getActivity(
                        this,
                        100,
                        openIntent,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.mipmap.ic_launcher_round)
                .setContentTitle("SumiTalk 正在运行")
                .setContentText("悬浮球与后台感知已启用")
                .setContentIntent(pi)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .build();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel =
                new NotificationChannel(CHANNEL_ID, "SumiTalk 常驻服务", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("用于悬浮球和后台状态感知");
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(channel);
        }
    }

    /** Respect user toggle: hide overlay but keep foreground service running. */
    private void applyOverlayVisibility() {
        if (!prefs.getBoolean(PREF_OVERLAY_VISIBLE, true)) {
            removeOverlay();
            return;
        }
        ensureOverlay();
    }

    private void ensureOverlay() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !android.provider.Settings.canDrawOverlays(this)) {
            removeOverlay();
            return;
        }
        if (overlayView != null) return;
        if (windowManager == null) return;

        int size = dp(52);
        overlayView = new ImageView(this);
        overlayView.setImageResource(R.drawable.sumi_floating_ball);
        overlayView.setScaleType(ImageView.ScaleType.CENTER_CROP);
        overlayView.setAdjustViewBounds(false);
        GradientDrawable bg = new GradientDrawable();
        bg.setShape(GradientDrawable.OVAL);
        bg.setColor(0xF2FFFFFF);
        bg.setStroke(dp(1), 0x22000000);
        overlayView.setBackground(bg);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            overlayView.setClipToOutline(true);
            overlayView.setOutlineProvider(ViewOutlineProvider.BACKGROUND);
        }

        overlayParams =
                new WindowManager.LayoutParams(
                        size,
                        size,
                        Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                                : WindowManager.LayoutParams.TYPE_PHONE,
                        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                                | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                        PixelFormat.TRANSLUCENT);
        overlayParams.gravity = Gravity.TOP | Gravity.START;
        applySavedOrDefaultOverlayPosition();

        overlayView.setOnTouchListener(new FloatingTouchListener());
        try {
            windowManager.addView(overlayView, overlayParams);
        } catch (Exception e) {
            Log.w(TAG, "add overlay failed", e);
            overlayView = null;
            overlayParams = null;
        }
    }

    private void removeOverlay() {
        if (overlayView == null || windowManager == null) return;
        try {
            windowManager.removeView(overlayView);
        } catch (Exception ignored) {
        }
        overlayView = null;
        overlayParams = null;
    }

    private void registerScreenStateReceiver() {
        if (screenStateReceiver != null) return;
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_SCREEN_OFF);
        filter.addAction(Intent.ACTION_USER_PRESENT);
        screenStateReceiver =
                new BroadcastReceiver() {
                    @Override
                    public void onReceive(Context context, Intent intent) {
                        String action = intent != null ? String.valueOf(intent.getAction()) : "";
                        if (Intent.ACTION_SCREEN_ON.equals(action)) {
                            reportScreenState("screen_on");
                        } else if (Intent.ACTION_SCREEN_OFF.equals(action)) {
                            reportScreenState("screen_off");
                        } else if (Intent.ACTION_USER_PRESENT.equals(action)) {
                            reportScreenState("user_present");
                        }
                    }
                };
        registerReceiver(screenStateReceiver, filter);
    }

    private void registerConfigChangeReceiver() {
        if (configChangeReceiver != null) return;
        configChangeReceiver =
                new BroadcastReceiver() {
                    @Override
                    public void onReceive(Context context, Intent intent) {
                        if (!prefs.getBoolean(PREF_OVERLAY_VISIBLE, true)) return;
                        if (overlayView == null || overlayParams == null || windowManager == null) return;
                        clampOverlayIntoScreen();
                        try {
                            windowManager.updateViewLayout(overlayView, overlayParams);
                        } catch (Exception ignored) {
                        }
                        saveOverlayPosition();
                    }
                };
        IntentFilter filter = new IntentFilter(Intent.ACTION_CONFIGURATION_CHANGED);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(configChangeReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(configChangeReceiver, filter);
        }
    }

    private int overlayBallPx() {
        return dp(52);
    }

    private int overlayMarginPx() {
        return dp(12);
    }

    private void getScreenPixels(Point out) {
        if (windowManager == null || out == null) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Rect b = windowManager.getCurrentWindowMetrics().getBounds();
            out.x = b.width();
            out.y = b.height();
        } else {
            DisplayMetrics dm = new DisplayMetrics();
            windowManager.getDefaultDisplay().getRealMetrics(dm);
            out.x = dm.widthPixels;
            out.y = dm.heightPixels;
        }
    }

    /** Keep the ball fully on screen (rotation / inset changes). */
    private void clampOverlayIntoScreen() {
        if (overlayParams == null) return;
        Point sz = new Point();
        getScreenPixels(sz);
        if (sz.x <= 0 || sz.y <= 0) return;
        int ball = overlayBallPx();
        int m = overlayMarginPx();
        overlayParams.x = Math.max(m, Math.min(overlayParams.x, sz.x - ball - m));
        overlayParams.y = Math.max(m, Math.min(overlayParams.y, sz.y - ball - m));
    }

    /** After drag: snap to left or right edge (吸边), ball stays fully visible. */
    private void snapOverlayToNearestVerticalEdge() {
        if (overlayParams == null) return;
        Point sz = new Point();
        getScreenPixels(sz);
        if (sz.x <= 0) return;
        int ball = overlayBallPx();
        int m = overlayMarginPx();
        int centerX = overlayParams.x + ball / 2;
        if (centerX * 2 <= sz.x) {
            overlayParams.x = m;
        } else {
            overlayParams.x = sz.x - ball - m;
        }
        clampOverlayIntoScreen();
    }

    private void saveOverlayPosition() {
        if (overlayParams == null) return;
        prefs.edit().putInt(PREF_OVERLAY_X, overlayParams.x).putInt(PREF_OVERLAY_Y, overlayParams.y).apply();
    }

    private void applySavedOrDefaultOverlayPosition() {
        if (overlayParams == null) return;
        int defX = dp(12);
        int defY = dp(240);
        if (prefs.contains(PREF_OVERLAY_X)) {
            overlayParams.x = prefs.getInt(PREF_OVERLAY_X, defX);
            overlayParams.y = prefs.getInt(PREF_OVERLAY_Y, defY);
        } else {
            overlayParams.x = defX;
            overlayParams.y = defY;
        }
        clampOverlayIntoScreen();
    }

    private void reportScreenState(String eventType) {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    HttpURLConnection conn = null;
                    try {
                        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
                        boolean interactive = pm != null && pm.isInteractive();
                        JSONObject payload = new JSONObject();
                        payload.put("event", eventType);
                        payload.put("device_id", panelDeviceId);
                        payload.put("interactive", interactive);
                        payload.put("occurred_at", nowIso());

                        URL url = new URL(API_BASE + "/miniapp-api/device-state/screen");
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
                            Log.w(TAG, "screen state non-2xx code=" + code);
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "reportScreenState failed", e);
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                });
    }

    private String nowIso() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date());
    }

    private int dp(int value) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, value, getResources().getDisplayMetrics()));
    }

    private void openApp() {
        Intent openIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (openIntent == null) {
            openIntent = new Intent(this, MainActivity.class);
        }
        openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        startActivity(openIntent);
    }

    private final class FloatingTouchListener implements View.OnTouchListener {
        private int startX;
        private int startY;
        private float touchStartX;
        private float touchStartY;
        private boolean dragging;

        @Override
        public boolean onTouch(View v, MotionEvent event) {
            if (overlayParams == null || windowManager == null) return false;
            switch (event.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    startX = overlayParams.x;
                    startY = overlayParams.y;
                    touchStartX = event.getRawX();
                    touchStartY = event.getRawY();
                    dragging = false;
                    return true;
                case MotionEvent.ACTION_MOVE:
                    int dx = Math.round(event.getRawX() - touchStartX);
                    int dy = Math.round(event.getRawY() - touchStartY);
                    if (!dragging && (Math.abs(dx) > dp(4) || Math.abs(dy) > dp(4))) {
                        dragging = true;
                    }
                    overlayParams.x = startX + dx;
                    overlayParams.y = startY + dy;
                    clampOverlayIntoScreen();
                    windowManager.updateViewLayout(overlayView, overlayParams);
                    return true;
                case MotionEvent.ACTION_UP:
                case MotionEvent.ACTION_CANCEL:
                    if (dragging) {
                        snapOverlayToNearestVerticalEdge();
                        try {
                            windowManager.updateViewLayout(overlayView, overlayParams);
                        } catch (Exception ignored) {
                        }
                        saveOverlayPosition();
                    } else {
                        openApp();
                    }
                    return true;
                default:
                    return false;
            }
        }
    }
}
