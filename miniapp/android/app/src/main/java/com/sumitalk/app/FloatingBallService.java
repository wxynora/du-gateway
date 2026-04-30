package com.sumitalk.app;

import android.app.AlertDialog;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.PixelFormat;
import android.graphics.Point;
import android.graphics.Rect;
import android.graphics.drawable.GradientDrawable;
import android.location.Criteria;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.net.Uri;
import android.content.pm.ServiceInfo;
import android.util.DisplayMetrics;
import android.os.Build;
import android.os.BatteryManager;
import android.os.IBinder;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.AlarmClock;
import android.provider.CalendarContract;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewOutlineProvider;
import android.view.WindowManager;
import android.widget.ImageView;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;
import android.Manifest;
import android.content.pm.PackageManager;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
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
    public static final String PREF_APP_VISIBLE = "app_visible";
    public static final String PREF_LAST_HISTORY_MESSAGE_KEY = "last_history_message_key";
    private static final String PREF_LAST_REPORTED_LOCATION_LAT = "last_reported_location_lat";
    private static final String PREF_LAST_REPORTED_LOCATION_LNG = "last_reported_location_lng";
    private static final String PREF_SCREEN_OFF_SINCE_MS = "screen_off_since_ms";

    private static final String TAG = "SumiTalkOverlay";
    private static final String API_BASE = "https://duxy-home.com";
    private static final String CHANNEL_ID = "sumitalk_overlay";
    private static final String MESSAGE_CHANNEL_ID = "sumitalk_message";
    private static final int NOTIFICATION_ID = 2001;
    private static final long HISTORY_POLL_INTERVAL_MS = 20000L;
    private static final long LOCATION_REPORT_INTERVAL_MS = 15L * 60L * 1000L;
    private static final long SCREEN_STATE_REPORT_INTERVAL_MS = 5L * 60L * 1000L;
    private static final long LOCATION_MAX_STALE_MS = 6L * 60L * 60L * 1000L;
    private static final float LOCATION_REPORT_MIN_DISTANCE_M = 5000f;

    private final ExecutorService ioExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private WindowManager windowManager;
    private ImageView overlayView;
    private WindowManager.LayoutParams overlayParams;
    private BroadcastReceiver screenStateReceiver;
    private BroadcastReceiver configChangeReceiver;
    private SharedPreferences prefs;
    private String panelToken = "";
    private String panelDeviceId = "";
    private final Runnable historyPollRunnable =
            new Runnable() {
                @Override
                public void run() {
                    pollLatestAssistantMessage();
                    pollPendingDeviceActions();
                    reportBatterySnapshot();
                    mainHandler.postDelayed(this, HISTORY_POLL_INTERVAL_MS);
                }
            };
    private final Runnable locationReportRunnable =
            new Runnable() {
                @Override
                public void run() {
                    reportLocationSnapshot();
                    mainHandler.postDelayed(this, LOCATION_REPORT_INTERVAL_MS);
                }
            };
    private final Runnable screenStateReportRunnable =
            new Runnable() {
                @Override
                public void run() {
                    reportScreenOffSnapshotIfNeeded();
                    mainHandler.postDelayed(this, SCREEN_STATE_REPORT_INTERVAL_MS);
                }
            };

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        restorePanelState();
        createNotificationChannel();
        startForegroundNotification(false);
        registerScreenStateReceiver();
        registerConfigChangeReceiver();
        applyOverlayVisibility();
        scheduleHistoryPolling();
        scheduleLocationReporting();
        scheduleScreenStateReporting();
        reportBatterySnapshot();
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
        scheduleHistoryPolling();
        scheduleLocationReporting();
        scheduleScreenStateReporting();
        reportBatterySnapshot();
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
        mainHandler.removeCallbacksAndMessages(null);
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

    private void startForegroundNotification(boolean includeLocationType) {
        Notification notification = buildNotification();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
                if (includeLocationType && hasLocationPermission()) {
                    type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
                }
                startForeground(NOTIFICATION_ID, notification, type);
                return;
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && includeLocationType && hasLocationPermission()) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
                return;
            }
        } catch (Exception e) {
            Log.w(TAG, "startForeground with location type failed", e);
        }
        startForeground(NOTIFICATION_ID, notification);
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationChannel channel =
                new NotificationChannel(CHANNEL_ID, "SumiTalk 常驻服务", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("用于悬浮球和后台状态感知");
        NotificationChannel messageChannel =
                new NotificationChannel(MESSAGE_CHANNEL_ID, "SumiTalk 消息提醒", NotificationManager.IMPORTANCE_HIGH);
        messageChannel.setDescription("用于助手新消息弹出提醒");
        messageChannel.enableVibration(true);
        messageChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(channel);
            nm.createNotificationChannel(messageChannel);
        }
    }

    private void scheduleHistoryPolling() {
        mainHandler.removeCallbacks(historyPollRunnable);
        mainHandler.post(historyPollRunnable);
    }

    private void scheduleLocationReporting() {
        mainHandler.removeCallbacks(locationReportRunnable);
        mainHandler.post(locationReportRunnable);
    }

    private void scheduleScreenStateReporting() {
        mainHandler.removeCallbacks(screenStateReportRunnable);
        mainHandler.post(screenStateReportRunnable);
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

    private boolean hasLocationPermission() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    private String chooseLocationProvider(LocationManager lm) {
        if (lm == null) return "";
        Criteria criteria = new Criteria();
        criteria.setAccuracy(Criteria.ACCURACY_COARSE);
        String provider = lm.getBestProvider(criteria, true);
        if (provider != null && !provider.trim().isEmpty()) return provider;
        if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) return LocationManager.NETWORK_PROVIDER;
        if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) return LocationManager.GPS_PROVIDER;
        if (lm.isProviderEnabled(LocationManager.PASSIVE_PROVIDER)) return LocationManager.PASSIVE_PROVIDER;
        return "";
    }

    private Location getBestLastKnownLocation(LocationManager lm) {
        Location best = null;
        try {
            List<String> providers = lm.getProviders(true);
            if (providers == null) return null;
            long now = System.currentTimeMillis();
            for (String provider : providers) {
                Location loc = lm.getLastKnownLocation(provider);
                if (loc == null) continue;
                long age = Math.max(0L, now - loc.getTime());
                if (age > LOCATION_MAX_STALE_MS) continue;
                if (best == null || loc.getAccuracy() < best.getAccuracy() || loc.getTime() > best.getTime()) {
                    best = loc;
                }
            }
        } catch (SecurityException ignored) {
        } catch (Exception e) {
            Log.w(TAG, "getBestLastKnownLocation failed", e);
        }
        return best;
    }

    private void reportLocationSnapshot() {
        if (panelToken.isEmpty() || !hasLocationPermission()) return;
        startForegroundNotification(true);
        LocationManager lm = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        if (lm == null) return;

        Location cached = getBestLastKnownLocation(lm);
        if (cached != null) {
            postLocation(cached, "last_known");
        }

        String provider = chooseLocationProvider(lm);
        if (provider.isEmpty()) return;
        try {
            lm.requestSingleUpdate(
                    provider,
                    new LocationListener() {
                        @Override
                        public void onLocationChanged(Location location) {
                            postLocation(location, "single_update");
                        }

                        @Override
                        public void onStatusChanged(String provider, int status, android.os.Bundle extras) {
                        }

                        @Override
                        public void onProviderEnabled(String provider) {
                        }

                        @Override
                        public void onProviderDisabled(String provider) {
                        }
                    },
                    Looper.getMainLooper());
        } catch (SecurityException ignored) {
        } catch (Exception e) {
            Log.w(TAG, "request location update failed", e);
        }
    }

    private void postLocation(Location location, String source) {
        if (location == null || panelToken.isEmpty()) return;
        if (!shouldReportLocation(location)) return;
        ioExecutor.execute(
                () -> {
                    try {
                        JSONObject payload = new JSONObject();
                        payload.put("device_id", panelDeviceId);
                        payload.put("lat", location.getLatitude());
                        payload.put("lng", location.getLongitude());
                        payload.put("accuracy", location.getAccuracy());
                        payload.put("provider", String.valueOf(location.getProvider()));
                        payload.put("source", source);
                        payload.put("captured_at", nowIso());
                        if (location.hasAltitude()) payload.put("altitude", location.getAltitude());
                        if (location.hasSpeed()) payload.put("speed", location.getSpeed());
                        if (location.hasBearing()) payload.put("bearing", location.getBearing());
                        postJson("/miniapp-api/device-state/location", payload);
                        saveLastReportedLocation(location);
                    } catch (Exception e) {
                        Log.w(TAG, "postLocation failed", e);
                    }
                });
    }

    private boolean shouldReportLocation(Location location) {
        if (location == null || prefs == null) return false;
        String latRaw = String.valueOf(prefs.getString(PREF_LAST_REPORTED_LOCATION_LAT, "")).trim();
        String lngRaw = String.valueOf(prefs.getString(PREF_LAST_REPORTED_LOCATION_LNG, "")).trim();
        if (latRaw.isEmpty() || lngRaw.isEmpty()) return true;
        try {
            Location last = new Location("last_reported");
            last.setLatitude(Double.parseDouble(latRaw));
            last.setLongitude(Double.parseDouble(lngRaw));
            return last.distanceTo(location) >= LOCATION_REPORT_MIN_DISTANCE_M;
        } catch (Exception ignored) {
            return true;
        }
    }

    private void saveLastReportedLocation(Location location) {
        if (location == null || prefs == null) return;
        prefs.edit()
                .putString(PREF_LAST_REPORTED_LOCATION_LAT, String.valueOf(location.getLatitude()))
                .putString(PREF_LAST_REPORTED_LOCATION_LNG, String.valueOf(location.getLongitude()))
                .apply();
    }

    private void reportScreenState(String eventType) {
        if (panelToken.isEmpty()) return;
        long observedAtMs = System.currentTimeMillis();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        boolean interactive = pm != null && pm.isInteractive();
        long occurredAtMs = observedAtMs;
        long screenOffSinceMs = 0L;
        if ("screen_off".equals(eventType)) {
            screenOffSinceMs = rememberScreenOffSince(observedAtMs);
            occurredAtMs = screenOffSinceMs;
        } else if ("screen_on".equals(eventType) || "user_present".equals(eventType) || ("app_active".equals(eventType) && interactive)) {
            clearScreenOffSince();
        }
        postScreenState(eventType, interactive, occurredAtMs, observedAtMs, false);
    }

    private void reportScreenOffSnapshotIfNeeded() {
        if (panelToken.isEmpty()) return;
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        boolean interactive = pm != null && pm.isInteractive();
        if (interactive) return;
        long observedAtMs = System.currentTimeMillis();
        long screenOffSinceMs = rememberScreenOffSince(observedAtMs);
        postScreenState("screen_off", false, screenOffSinceMs, observedAtMs, true);
    }

    private long rememberScreenOffSince(long fallbackMs) {
        long existing = 0L;
        try {
            existing = prefs.getLong(PREF_SCREEN_OFF_SINCE_MS, 0L);
        } catch (Exception ignored) {
        }
        if (existing <= 0L || existing > fallbackMs) {
            existing = fallbackMs;
            try {
                prefs.edit().putLong(PREF_SCREEN_OFF_SINCE_MS, existing).apply();
            } catch (Exception ignored) {
            }
        }
        return existing;
    }

    private void clearScreenOffSince() {
        try {
            prefs.edit().remove(PREF_SCREEN_OFF_SINCE_MS).apply();
        } catch (Exception ignored) {
        }
    }

    private void postScreenState(String eventType, boolean interactive, long occurredAtMs, long observedAtMs, boolean snapshot) {
        ioExecutor.execute(
                () -> {
                    try {
                        JSONObject payload = new JSONObject();
                        payload.put("event", eventType);
                        payload.put("device_id", panelDeviceId);
                        payload.put("interactive", interactive);
                        payload.put("occurred_at", isoFromMillis(occurredAtMs));
                        payload.put("observed_at", isoFromMillis(observedAtMs));
                        payload.put("snapshot", snapshot);
                        if ("screen_off".equals(eventType) && occurredAtMs > 0L) {
                            payload.put("screen_off_since", isoFromMillis(occurredAtMs));
                            payload.put("screen_off_duration_ms", Math.max(0L, observedAtMs - occurredAtMs));
                        }
                        postJson("/miniapp-api/device-state/screen", payload);
                    } catch (Exception e) {
                        Log.w(TAG, "reportScreenState failed", e);
                    }
                });
    }

    private void reportBatterySnapshot() {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    try {
                        Intent battery = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
                        if (battery == null) return;
                        int level = battery.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                        int scale = battery.getIntExtra(BatteryManager.EXTRA_SCALE, -1);
                        if (level < 0 || scale <= 0) return;
                        int percent = Math.max(0, Math.min(100, Math.round(level * 100f / scale)));
                        int status = battery.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                        boolean charging = status == BatteryManager.BATTERY_STATUS_CHARGING
                                || status == BatteryManager.BATTERY_STATUS_FULL;
                        JSONObject payload = new JSONObject();
                        payload.put("device_id", panelDeviceId);
                        payload.put("level", percent);
                        payload.put("charging", charging);
                        payload.put("captured_at", nowIso());
                        postJson("/miniapp-api/device-state/battery", payload);
                    } catch (Exception e) {
                        Log.w(TAG, "reportBatterySnapshot failed", e);
                    }
                });
    }

    private void pollLatestAssistantMessage() {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(API_BASE + "/miniapp-api/sumitalk-history");
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(10000);
                        conn.setReadTimeout(10000);
                        conn.setRequestProperty("Authorization", "Bearer " + panelToken);
                        int code = conn.getResponseCode();
                        if (code < 200 || code >= 300) {
                            Log.w(TAG, "pollLatestAssistantMessage non-2xx code=" + code);
                            return;
                        }
                        String body = readAllText(conn.getInputStream());
                        JSONObject root = new JSONObject(body);
                        JSONArray messages = root.optJSONArray("messages");
                        if (messages == null || messages.length() <= 0) return;
                        String latestKey = "";
                        String latestPreview = "";
                        for (int i = messages.length() - 1; i >= 0; i -= 1) {
                            JSONObject item = messages.optJSONObject(i);
                            if (item == null) continue;
                            if (!"assistant".equals(String.valueOf(item.optString("role", "")).trim())) continue;
                            String content = messageContentToText(item.opt("content"));
                            if (content.isEmpty()) continue;
                            String id = String.valueOf(item.optString("id", "")).trim();
                            String createdAt = String.valueOf(item.optString("createdAt", "")).trim();
                            latestKey = !id.isEmpty() ? id : createdAt + "|" + content.hashCode();
                            latestPreview = content;
                            break;
                        }
                        if (latestKey.isEmpty() || latestPreview.isEmpty()) return;
                        String previousKey = String.valueOf(prefs.getString(PREF_LAST_HISTORY_MESSAGE_KEY, "")).trim();
                        if (previousKey.isEmpty()) {
                            prefs.edit().putString(PREF_LAST_HISTORY_MESSAGE_KEY, latestKey).apply();
                            return;
                        }
                        if (latestKey.equals(previousKey)) return;
                        prefs.edit().putString(PREF_LAST_HISTORY_MESSAGE_KEY, latestKey).apply();
                        if (!prefs.getBoolean(PREF_APP_VISIBLE, false)) {
                            showMessagePopup(latestPreview);
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "pollLatestAssistantMessage failed", e);
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                });
    }

    private void pollPendingDeviceActions() {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(API_BASE + "/miniapp-api/device-actions?limit=5");
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(10000);
                        conn.setReadTimeout(10000);
                        conn.setRequestProperty("Authorization", "Bearer " + panelToken);
                        int code = conn.getResponseCode();
                        if (code < 200 || code >= 300) {
                            Log.w(TAG, "pollPendingDeviceActions non-2xx code=" + code);
                            return;
                        }
                        JSONObject root = new JSONObject(readAllText(conn.getInputStream()));
                        JSONArray actions = root.optJSONArray("actions");
                        if (actions == null || actions.length() <= 0) return;
                        JSONArray results = new JSONArray();
                        for (int i = 0; i < actions.length(); i += 1) {
                            JSONObject action = actions.optJSONObject(i);
                            if (action == null) continue;
                            results.put(executeDeviceAction(action));
                        }
                        if (results.length() <= 0) return;
                        JSONObject payload = new JSONObject();
                        payload.put("results", results);
                        postJson("/miniapp-api/device-actions/done", payload);
                    } catch (Exception e) {
                        Log.w(TAG, "pollPendingDeviceActions failed", e);
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                });
    }

    private JSONObject executeDeviceAction(JSONObject action) {
        JSONObject result = new JSONObject();
        String id = String.valueOf(action.optString("id", "")).trim();
        try {
            result.put("id", id);
            String type = String.valueOf(action.optString("type", "")).trim();
            JSONObject payload = action.optJSONObject("payload");
            if ("create_system_alarm".equals(type)) {
                JSONObject detail = createSystemAlarmFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                return result;
            }
            if ("create_calendar_event".equals(type)) {
                JSONObject detail = createCalendarEventFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                return result;
            }
            if ("show_choice_dialog".equals(type)) {
                JSONObject detail = showChoiceDialogFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                return result;
            }
            result.put("status", "failed");
            result.put("error", "unknown_action");
            return result;
        } catch (Exception e) {
            try {
                result.put("status", "failed");
                result.put("error", e.getMessage() == null ? String.valueOf(e) : e.getMessage());
            } catch (Exception ignored) {
            }
            return result;
        }
    }

    private JSONObject createSystemAlarmFromAction(JSONObject payload) throws Exception {
        int hour = payload.optInt("hour", -1);
        int minute = payload.optInt("minute", -1);
        if (hour < 0 || hour > 23) throw new IllegalArgumentException("invalid_hour");
        if (minute < 0 || minute > 59) throw new IllegalArgumentException("invalid_minute");
        String title = String.valueOf(payload.optString("title", "渡的提醒")).trim();
        if (title.isEmpty()) title = "渡的提醒";
        boolean appVisible = prefs.getBoolean(PREF_APP_VISIBLE, false);
        boolean skipUi = appVisible || payload.optBoolean("skipUi", false);
        boolean notify = payload.optBoolean("notify", true) && !appVisible;

        Intent intent =
                new Intent(AlarmClock.ACTION_SET_ALARM)
                        .putExtra(AlarmClock.EXTRA_HOUR, hour)
                        .putExtra(AlarmClock.EXTRA_MINUTES, minute)
                        .putExtra(AlarmClock.EXTRA_MESSAGE, title)
                        .putExtra(AlarmClock.EXTRA_SKIP_UI, skipUi)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(intent);
        if (notify) {
            showSystemAlarmCreatedNotification(hour, minute, title);
        }
        JSONObject detail = new JSONObject();
        detail.put("hour", hour);
        detail.put("minute", minute);
        detail.put("title", title);
        detail.put("notified", notify);
        return detail;
    }

    private JSONObject showChoiceDialogFromAction(JSONObject payload) throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !android.provider.Settings.canDrawOverlays(this)) {
            throw new IllegalStateException("overlay_permission_denied");
        }
        final String title = String.valueOf(payload.optString("title", "渡")).trim();
        final String message = String.valueOf(payload.optString("message", "")).trim();
        if (message.isEmpty()) throw new IllegalArgumentException("message_empty");
        final String level = String.valueOf(payload.optString("level", "info")).trim();
        final boolean dismissible = payload.optBoolean("dismissible", true);
        final int timeoutSeconds = Math.max(30, Math.min(1800, payload.optInt("timeoutSeconds", 600)));

        JSONArray choices = payload.optJSONArray("choices");
        String choiceAId = "choice_a";
        String choiceALabel = "好的";
        String choiceBId = "choice_b";
        String choiceBLabel = "知道了";
        if (choices != null && choices.length() >= 2) {
            JSONObject a = choices.optJSONObject(0);
            JSONObject b = choices.optJSONObject(1);
            if (a != null) {
                choiceAId = String.valueOf(a.optString("id", "choice_a")).trim();
                choiceALabel = String.valueOf(a.optString("label", choiceALabel)).trim();
            }
            if (b != null) {
                choiceBId = String.valueOf(b.optString("id", "choice_b")).trim();
                choiceBLabel = String.valueOf(b.optString("label", choiceBLabel)).trim();
            }
        }
        if (choiceAId.isEmpty()) choiceAId = "choice_a";
        if (choiceBId.isEmpty()) choiceBId = "choice_b";
        if (choiceALabel.isEmpty()) choiceALabel = "好的";
        if (choiceBLabel.isEmpty()) choiceBLabel = "知道了";

        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<JSONObject> resultRef = new AtomicReference<>();
        AtomicReference<AlertDialog> dialogRef = new AtomicReference<>();
        final String finalChoiceAId = choiceAId;
        final String finalChoiceALabel = choiceALabel;
        final String finalChoiceBId = choiceBId;
        final String finalChoiceBLabel = choiceBLabel;
        mainHandler.post(
                () -> {
                    try {
                        AlertDialog dialog =
                                new AlertDialog.Builder(this)
                                        .setTitle(title.isEmpty() ? "渡" : title)
                                        .setMessage(message)
                                        .setPositiveButton(
                                                finalChoiceALabel,
                                                (d, which) ->
                                                        completeChoiceDialog(
                                                                resultRef,
                                                                latch,
                                                                buildChoiceDialogResult(finalChoiceAId, finalChoiceALabel, level, false, false)))
                                        .setNegativeButton(
                                                finalChoiceBLabel,
                                                (d, which) ->
                                                        completeChoiceDialog(
                                                                resultRef,
                                                                latch,
                                                                buildChoiceDialogResult(finalChoiceBId, finalChoiceBLabel, level, false, false)))
                                        .create();
                        dialog.setCancelable(dismissible);
                        dialog.setCanceledOnTouchOutside(dismissible);
                        dialog.setOnCancelListener(
                                d ->
                                        completeChoiceDialog(
                                                resultRef,
                                                latch,
                                                buildChoiceDialogResult("dismissed", "", level, true, false)));
                        android.view.Window window = dialog.getWindow();
                        if (window == null) throw new IllegalStateException("dialog_window_unavailable");
                        window.setType(
                                Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                                        ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                                        : WindowManager.LayoutParams.TYPE_PHONE);
                        dialogRef.set(dialog);
                        dialog.show();
                    } catch (Exception e) {
                        completeChoiceDialog(resultRef, latch, buildChoiceDialogError(e));
                    }
                });
        if (!latch.await(timeoutSeconds, TimeUnit.SECONDS)) {
            resultRef.compareAndSet(null, buildChoiceDialogResult("timeout", "", level, true, true));
            AlertDialog dialog = dialogRef.get();
            if (dialog != null) {
                mainHandler.post(
                        () -> {
                            try {
                                dialog.dismiss();
                            } catch (Exception ignored) {
                            }
                        });
            }
        }
        JSONObject detail = resultRef.get();
        if (detail == null) throw new IllegalStateException("dialog_no_result");
        String error = String.valueOf(detail.optString("error", "")).trim();
        if (!error.isEmpty()) throw new IllegalStateException(error);
        return detail;
    }

    private void completeChoiceDialog(AtomicReference<JSONObject> resultRef, CountDownLatch latch, JSONObject detail) {
        if (resultRef.compareAndSet(null, detail)) {
            latch.countDown();
        }
    }

    private JSONObject buildChoiceDialogResult(String choiceId, String label, String level, boolean dismissed, boolean timeout) {
        JSONObject detail = new JSONObject();
        try {
            detail.put("choice_id", choiceId);
            detail.put("label", label);
            detail.put("level", level);
            detail.put("dismissed", dismissed);
            detail.put("timeout", timeout);
        } catch (Exception ignored) {
        }
        return detail;
    }

    private JSONObject buildChoiceDialogError(Exception e) {
        JSONObject detail = new JSONObject();
        try {
            detail.put("error", e.getMessage() == null ? String.valueOf(e) : e.getMessage());
        } catch (Exception ignored) {
        }
        return detail;
    }

    private boolean hasCalendarPermission() {
        return ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALENDAR) == PackageManager.PERMISSION_GRANTED
                && ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_CALENDAR) == PackageManager.PERMISSION_GRANTED;
    }

    private long resolveWritableCalendarId() throws Exception {
        if (!hasCalendarPermission()) throw new IllegalStateException("calendar_permission_denied");
        String[] projection = new String[] {
                CalendarContract.Calendars._ID,
                CalendarContract.Calendars.CALENDAR_DISPLAY_NAME,
                CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL,
        };
        String selection = CalendarContract.Calendars.VISIBLE + "!=0 AND "
                + CalendarContract.Calendars.CALENDAR_ACCESS_LEVEL + ">="
                + CalendarContract.Calendars.CAL_ACCESS_CONTRIBUTOR;
        try (Cursor cursor = getContentResolver().query(
                CalendarContract.Calendars.CONTENT_URI,
                projection,
                selection,
                null,
                CalendarContract.Calendars._ID + " ASC")) {
            if (cursor != null && cursor.moveToFirst()) {
                return cursor.getLong(0);
            }
        }
        throw new IllegalStateException("no_writable_calendar");
    }

    private JSONObject createCalendarEventFromAction(JSONObject payload) throws Exception {
        long startMillis = payload.optLong("startMillis", 0L);
        long endMillis = payload.optLong("endMillis", 0L);
        if (startMillis <= 0L) throw new IllegalArgumentException("invalid_start_time");
        if (endMillis <= startMillis) throw new IllegalArgumentException("invalid_end_time");
        String title = String.valueOf(payload.optString("title", "渡的行程")).trim();
        if (title.isEmpty()) title = "渡的行程";
        String description = String.valueOf(payload.optString("description", "")).trim();
        String location = String.valueOf(payload.optString("location", "")).trim();
        boolean allDay = payload.optBoolean("allDay", false);
        int reminderMinutes = payload.optInt("reminderMinutes", 10);
        boolean notify = payload.optBoolean("notify", true) && !prefs.getBoolean(PREF_APP_VISIBLE, false);

        long calendarId = resolveWritableCalendarId();
        ContentValues values = new ContentValues();
        values.put(CalendarContract.Events.CALENDAR_ID, calendarId);
        values.put(CalendarContract.Events.TITLE, title);
        values.put(CalendarContract.Events.DTSTART, startMillis);
        values.put(CalendarContract.Events.DTEND, endMillis);
        values.put(CalendarContract.Events.EVENT_TIMEZONE, TimeZone.getDefault().getID());
        values.put(CalendarContract.Events.ALL_DAY, allDay ? 1 : 0);
        values.put(CalendarContract.Events.HAS_ALARM, reminderMinutes >= 0 ? 1 : 0);
        if (!description.isEmpty()) values.put(CalendarContract.Events.DESCRIPTION, description);
        if (!location.isEmpty()) values.put(CalendarContract.Events.EVENT_LOCATION, location);

        Uri eventUri = getContentResolver().insert(CalendarContract.Events.CONTENT_URI, values);
        if (eventUri == null) throw new IllegalStateException("calendar_insert_failed");
        long eventId = ContentUris.parseId(eventUri);

        if (reminderMinutes >= 0) {
            ContentValues reminder = new ContentValues();
            reminder.put(CalendarContract.Reminders.EVENT_ID, eventId);
            reminder.put(CalendarContract.Reminders.MINUTES, reminderMinutes);
            reminder.put(CalendarContract.Reminders.METHOD, CalendarContract.Reminders.METHOD_ALERT);
            getContentResolver().insert(CalendarContract.Reminders.CONTENT_URI, reminder);
        }
        if (notify) {
            showCalendarEventCreatedNotification(eventId, startMillis, title);
        }

        JSONObject detail = new JSONObject();
        detail.put("eventId", eventId);
        detail.put("calendarId", calendarId);
        detail.put("title", title);
        detail.put("startMillis", startMillis);
        detail.put("endMillis", endMillis);
        detail.put("notified", notify);
        return detail;
    }

    private Intent buildOpenCalendarEventIntent(long eventId, long startMillis) {
        Uri uri = eventId > 0L
                ? ContentUris.withAppendedId(CalendarContract.Events.CONTENT_URI, eventId)
                : Uri.parse("content://com.android.calendar/time/" + Math.max(1L, startMillis));
        return new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    private void showCalendarEventCreatedNotification(long eventId, long startMillis, String title) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        PendingIntent pi =
                PendingIntent.getActivity(
                        this,
                        (int) (System.currentTimeMillis() & 0x7fffffff),
                        buildOpenCalendarEventIntent(eventId, startMillis),
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification notification =
                new NotificationCompat.Builder(this, MESSAGE_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle("已创建系统行程")
                        .setContentText(title)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(title))
                        .setContentIntent(pi)
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setCategory(NotificationCompat.CATEGORY_EVENT)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .build();
        NotificationManagerCompat.from(this)
                .notify((int) (System.currentTimeMillis() & 0x7fffffff), notification);
    }

    private void showSystemAlarmCreatedNotification(int hour, int minute, String title) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        Intent openIntent = new Intent(AlarmClock.ACTION_SHOW_ALARMS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi =
                PendingIntent.getActivity(
                        this,
                        (int) (System.currentTimeMillis() & 0x7fffffff),
                        openIntent,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String time = String.format(Locale.US, "%02d:%02d", hour, minute);
        Notification notification =
                new NotificationCompat.Builder(this, MESSAGE_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle("已创建系统闹钟")
                        .setContentText(time + " " + title)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(time + " " + title))
                        .setContentIntent(pi)
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setCategory(NotificationCompat.CATEGORY_REMINDER)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .build();
        NotificationManagerCompat.from(this)
                .notify((int) (System.currentTimeMillis() & 0x7fffffff), notification);
    }

    private void showMessagePopup(String preview) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        != PackageManager.PERMISSION_GRANTED) {
            return;
        }
        Intent openIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (openIntent == null) {
            openIntent = new Intent(this, MainActivity.class);
        }
        openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi =
                PendingIntent.getActivity(
                        this,
                        (int) (System.currentTimeMillis() & 0x7fffffff),
                        openIntent,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String text = preview.length() > 120 ? preview.substring(0, 120) + "…" : preview;
        Notification notification =
                new NotificationCompat.Builder(this, MESSAGE_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle("渡")
                        .setContentText(text)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                        .setContentIntent(pi)
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setCategory(NotificationCompat.CATEGORY_MESSAGE)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .build();
        NotificationManagerCompat.from(this)
                .notify((int) (System.currentTimeMillis() & 0x7fffffff), notification);
    }

    private String readAllText(InputStream is) throws Exception {
        ByteArrayOutputStream os = new ByteArrayOutputStream();
        byte[] buf = new byte[2048];
        int n;
        while ((n = is.read(buf)) > 0) {
            os.write(buf, 0, n);
        }
        return new String(os.toByteArray(), java.nio.charset.StandardCharsets.UTF_8);
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

    private String messageContentToText(Object content) {
        if (content == null) return "";
        if (content instanceof String) return String.valueOf(content).trim();
        if (content instanceof JSONObject) {
            JSONObject obj = (JSONObject) content;
            String text = String.valueOf(obj.optString("text", "")).trim();
            if (!text.isEmpty()) return text;
            String inner = String.valueOf(obj.optString("content", "")).trim();
            if (!inner.isEmpty()) return inner;
            Object innerContent = obj.opt("content");
            if (innerContent != null && innerContent != obj) {
                return messageContentToText(innerContent);
            }
            return "";
        }
        if (content instanceof JSONArray) {
            JSONArray arr = (JSONArray) content;
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < arr.length(); i += 1) {
                String part = messageContentToText(arr.opt(i));
                if (part.isEmpty()) continue;
                if (sb.length() > 0) sb.append('\n');
                sb.append(part);
            }
            return sb.toString().trim();
        }
        return String.valueOf(content).trim();
    }

    private String nowIso() {
        return isoFromMillis(System.currentTimeMillis());
    }

    private String isoFromMillis(long millis) {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US);
        fmt.setTimeZone(TimeZone.getDefault());
        return fmt.format(new java.util.Date(millis));
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
