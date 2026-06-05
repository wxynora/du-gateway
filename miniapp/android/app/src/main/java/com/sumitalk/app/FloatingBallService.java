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
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Point;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.ColorDrawable;
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
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
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
import java.net.URLEncoder;
import java.text.SimpleDateFormat;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import org.json.JSONArray;
import org.json.JSONObject;

public class FloatingBallService extends Service {
    public static final String ACTION_START_OR_UPDATE = "com.sumitalk.app.action.START_OR_UPDATE";
    public static final String ACTION_STOP = "com.sumitalk.app.action.STOP";
    public static final String ACTION_ENABLE_MEDIA_PROJECTION_FG = "com.sumitalk.app.action.ENABLE_MEDIA_PROJECTION_FG";
    public static final String ACTION_DISABLE_MEDIA_PROJECTION_FG = "com.sumitalk.app.action.DISABLE_MEDIA_PROJECTION_FG";
    public static final String ACTION_REQUEST_SENSE_SNAPSHOT = "com.sumitalk.app.action.REQUEST_SENSE_SNAPSHOT";
    public static final String EXTRA_PANEL_TOKEN = "panel_token";
    public static final String EXTRA_DEVICE_ID = "device_id";
    public static final String PREFS_NAME = "sumitalk_native_state";
    public static final String PREF_PANEL_TOKEN = "panel_token";
    public static final String PREF_DEVICE_ID = "device_id";
    public static final String PREF_OVERLAY_X = "overlay_x";
    public static final String PREF_OVERLAY_Y = "overlay_y";
    /** User preference: show floating ball (does not revoke overlay permission). */
    public static final String PREF_OVERLAY_VISIBLE = "overlay_visible";
    public static final String PREF_SENSE_REPORTING_ENABLED = "sense_reporting_enabled";
    public static final String PREF_APP_VISIBLE = "app_visible";
    public static final String PREF_LAST_HISTORY_MESSAGE_KEY = "last_history_message_key";
    private static final String PREF_LAST_REPORTED_LOCATION_LAT = "last_reported_location_lat";
    private static final String PREF_LAST_REPORTED_LOCATION_LNG = "last_reported_location_lng";
    private static final String PREF_SCREEN_OFF_SINCE_MS = "screen_off_since_ms";

    private static final String TAG = "SumiTalkOverlay";
    private static final String API_BASE = "https://duxy-home.com";
    private static final String CHANNEL_ID = "sumitalk_overlay";
    private static final String MESSAGE_CHANNEL_ID = "sumitalk_message";
    private static final String VOICE_CALL_CHANNEL_ID = "sumitalk_voice_call";
    private static final String SUMITALK_MAIN_WINDOW_ID = "sumitalk-main";
    private static final int NOTIFICATION_ID = 2001;
    private static final long HISTORY_POLL_INTERVAL_MS = 20000L;
    private static final long REALTIME_RECONNECT_BASE_MS = 3000L;
    private static final long REALTIME_RECONNECT_MAX_MS = 60000L;
    private static final long BATTERY_REPORT_INTERVAL_MS = 5L * 60L * 1000L;
    private static final long DU_VITALS_POLL_INTERVAL_MS = 60L * 1000L;
    private static final long LOCATION_REPORT_INTERVAL_MS = 15L * 60L * 1000L;
    private static final long SCREEN_STATE_REPORT_INTERVAL_MS = 5L * 60L * 1000L;
    private static final long LOCATION_MAX_STALE_MS = 2L * 60L * 1000L;
    private static final float LOCATION_REPORT_MIN_DISTANCE_M = 3000f;

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
    private long lastBatteryReportMs = 0L;
    private long lastDuVitalsPollMs = 0L;
    private OkHttpClient realtimeClient;
    private WebSocket realtimeSocket;
    private volatile boolean realtimeConnected = false;
    private volatile boolean realtimeConnecting = false;
    private volatile boolean realtimeReconnectScheduled = false;
    private volatile boolean serviceStopping = false;
    private int realtimeReconnectAttempts = 0;
    private final Runnable historyPollRunnable =
            new Runnable() {
                @Override
                public void run() {
                    ensureRealtimeWebSocket();
                    if (!realtimeConnected) {
                        pollLatestAssistantMessage();
                        pollPendingDeviceActions();
                    }
                    reportBatterySnapshotIfDue();
                    pollDuVitalsIfDue();
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
            serviceStopping = true;
            closeRealtimeWebSocket(false);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (ACTION_ENABLE_MEDIA_PROJECTION_FG.equals(action)) {
            startForegroundNotification(false, true);
            return START_STICKY;
        }
        if (ACTION_DISABLE_MEDIA_PROJECTION_FG.equals(action)) {
            startForegroundNotification(false, false);
            return START_STICKY;
        }
        if (ACTION_REQUEST_SENSE_SNAPSHOT.equals(action)) {
            serviceStopping = false;
            updatePanelState(intent);
            requestSenseSnapshot();
            return START_STICKY;
        }
        serviceStopping = false;
        updatePanelState(intent);
        applyOverlayVisibility();
        reportScreenState("app_active");
        scheduleHistoryPolling();
        scheduleLocationReporting();
        scheduleScreenStateReporting();
        reportBatterySnapshot();
        return START_STICKY;
    }

    public static boolean isSenseReportingEnabled(Context context) {
        if (context == null) return true;
        try {
            return context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .getBoolean(PREF_SENSE_REPORTING_ENABLED, true);
        } catch (Exception ignored) {
            return true;
        }
    }

    public static void setSenseReportingEnabled(Context context, boolean enabled) {
        if (context == null) return;
        try {
            context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .putBoolean(PREF_SENSE_REPORTING_ENABLED, enabled)
                    .apply();
        } catch (Exception ignored) {
        }
    }

    private boolean isSenseReportingEnabled() {
        return isSenseReportingEnabled(this);
    }

    private void requestSenseSnapshot() {
        if (!isSenseReportingEnabled()) return;
        reportBatterySnapshot();
        reportLocationSnapshot();
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        boolean interactive = pm != null && pm.isInteractive();
        if (interactive) {
            reportScreenState("app_active");
        } else {
            reportScreenOffSnapshotIfNeeded();
        }
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        serviceStopping = true;
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
        closeRealtimeWebSocket(true);
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
        String nextToken = intent.hasExtra(EXTRA_PANEL_TOKEN) ? String.valueOf(intent.getStringExtra(EXTRA_PANEL_TOKEN)).trim() : "";
        String nextDeviceId = intent.hasExtra(EXTRA_DEVICE_ID) ? String.valueOf(intent.getStringExtra(EXTRA_DEVICE_ID)).trim() : "";
        boolean changed = false;
        if (!nextToken.isEmpty() && !"null".equalsIgnoreCase(nextToken) && !nextToken.equals(panelToken)) {
            panelToken = nextToken;
            changed = true;
        }
        if (!nextDeviceId.isEmpty() && !"null".equalsIgnoreCase(nextDeviceId) && !nextDeviceId.equals(panelDeviceId)) {
            panelDeviceId = nextDeviceId;
            changed = true;
        }
        prefs.edit().putString(PREF_PANEL_TOKEN, panelToken).putString(PREF_DEVICE_ID, panelDeviceId).apply();
        if (changed) {
            lastDuVitalsPollMs = 0L;
            closeRealtimeWebSocket(false);
        }
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
        startForegroundNotification(includeLocationType, false);
    }

    private void startForegroundNotification(boolean includeLocationType, boolean includeMediaProjectionType) {
        Notification notification = buildNotification();
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                int type = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE;
                if (includeLocationType && hasLocationPermission()) {
                    type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
                }
                if (includeMediaProjectionType) {
                    type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;
                }
                startForeground(NOTIFICATION_ID, notification, type);
                return;
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                int type = 0;
                if (includeLocationType && hasLocationPermission()) {
                    type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION;
                }
                if (includeMediaProjectionType) {
                    type |= ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION;
                }
                if (type != 0) {
                    startForeground(NOTIFICATION_ID, notification, type);
                    return;
                }
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
        NotificationChannel voiceCallChannel =
                new NotificationChannel(VOICE_CALL_CHANNEL_ID, "渡来电", NotificationManager.IMPORTANCE_HIGH);
        voiceCallChannel.setDescription("用于渡主动发起的 SumiTalk 语音来电邀请");
        voiceCallChannel.enableVibration(true);
        voiceCallChannel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) {
            nm.createNotificationChannel(channel);
            nm.createNotificationChannel(messageChannel);
            nm.createNotificationChannel(voiceCallChannel);
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
                        overlayWindowType(),
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

    private int overlayWindowType() {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
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

    private boolean canUseOverlayWindow() {
        return windowManager != null
                && (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || android.provider.Settings.canDrawOverlays(this));
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
        if (!isSenseReportingEnabled() || panelToken.isEmpty() || !hasLocationPermission()) return;
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
        if (!isSenseReportingEnabled() || location == null || panelToken.isEmpty()) return;
        long locationAgeMs = location.getTime() > 0L ? Math.max(0L, System.currentTimeMillis() - location.getTime()) : 0L;
        if (location.getTime() > 0L && locationAgeMs > LOCATION_MAX_STALE_MS) return;
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
                        payload.put("captured_at", location.getTime() > 0L ? isoFromMillis(location.getTime()) : nowIso());
                        payload.put("reported_at", nowIso());
                        payload.put("location_age_ms", locationAgeMs);
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
        if (!isSenseReportingEnabled() || panelToken.isEmpty()) return;
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
        if (!isSenseReportingEnabled() || panelToken.isEmpty()) return;
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
        if (!isSenseReportingEnabled() || panelToken.isEmpty()) return;
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

    private void reportBatterySnapshotIfDue() {
        if (!isSenseReportingEnabled()) return;
        long now = System.currentTimeMillis();
        if (lastBatteryReportMs > 0 && now - lastBatteryReportMs < BATTERY_REPORT_INTERVAL_MS) {
            return;
        }
        lastBatteryReportMs = now;
        reportBatterySnapshot();
    }

    private void pollDuVitalsIfDue() {
        long now = System.currentTimeMillis();
        if (lastDuVitalsPollMs > 0 && now - lastDuVitalsPollMs < DU_VITALS_POLL_INTERVAL_MS) {
            return;
        }
        lastDuVitalsPollMs = now;
        pollDuVitals();
    }

    private void pollDuVitals() {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    HttpURLConnection conn = null;
                    try {
                        URL url = new URL(API_BASE + "/miniapp-api/device-state/health");
                        conn = (HttpURLConnection) url.openConnection();
                        conn.setRequestMethod("GET");
                        conn.setConnectTimeout(10000);
                        conn.setReadTimeout(10000);
                        conn.setRequestProperty("Authorization", "Bearer " + panelToken);
                        int code = conn.getResponseCode();
                        if (code < 200 || code >= 300) {
                            Log.w(TAG, "pollDuVitals non-2xx code=" + code);
                            return;
                        }
                        JSONObject root = new JSONObject(readAllText(conn.getInputStream()));
                        JSONObject vitals = root.optJSONObject("du_vitals");
                        if (vitals == null) return;
                        int heartBpm = vitals.optInt("heart_bpm", vitals.optInt("heartBpm", 0));
                        int breathRpm = vitals.optInt("breath_rpm", vitals.optInt("breathRpm", 0));
                        if (heartBpm <= 0 && breathRpm <= 0) return;
                        String updatedAt =
                                String.valueOf(
                                                vitals.optString(
                                                        "updatedAt",
                                                        vitals.optString("updated_at", vitals.optString("at", ""))))
                                        .trim();
                        DuVitalsNotification.show(
                                this,
                                heartBpm,
                                breathRpm,
                                vitals.optString("status", ""),
                                updatedAt);
                    } catch (Exception e) {
                        Log.w(TAG, "pollDuVitals failed", e);
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                });
    }

    private void pollLatestAssistantMessage() {
        if (panelToken.isEmpty()) return;
        ioExecutor.execute(
                () -> {
                    HttpURLConnection conn = null;
                    try {
                        String previousKey = String.valueOf(prefs.getString(PREF_LAST_HISTORY_MESSAGE_KEY, "")).trim();
                        String query = "?window_id=" + encodeQueryValue(SUMITALK_MAIN_WINDOW_ID)
                                + (previousKey.isEmpty() ? "" : "&after_key=" + encodeQueryValue(previousKey));
                        URL url = new URL(API_BASE + "/miniapp-api/sumitalk-history/latest" + query);
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
                        String latestKey = String.valueOf(root.optString("latest_key", "")).trim();
                        JSONArray messages = root.optJSONArray("messages");
                        JSONObject latestMessage = null;
                        if (messages != null && messages.length() > 0) {
                            latestMessage = messages.optJSONObject(0);
                        }
                        if (latestMessage == null) {
                            JSONObject msg = root.optJSONObject("message");
                            if (msg != null) latestMessage = msg;
                        }
                        if (latestMessage == null) {
                            if (!latestKey.isEmpty() && previousKey.isEmpty()) {
                                prefs.edit().putString(PREF_LAST_HISTORY_MESSAGE_KEY, latestKey).apply();
                            }
                            return;
                        }
                        String latestPreview = "";
                        if ("assistant".equals(String.valueOf(latestMessage.optString("role", "")).trim())) {
                            latestPreview = messageContentToText(latestMessage.opt("content"));
                            if (latestKey.isEmpty()) {
                                String id = String.valueOf(latestMessage.optString("id", "")).trim();
                                String createdAt = String.valueOf(latestMessage.optString("createdAt", "")).trim();
                                latestKey = !id.isEmpty() ? id : createdAt + "|" + latestPreview.hashCode();
                            }
                        }
                        if (latestKey.isEmpty() || latestPreview.isEmpty()) return;
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
                        Log.i(TAG, "device_actions poll received count=" + actions.length() + " deviceId=" + panelDeviceId);
                        JSONArray results = new JSONArray();
                        for (int i = 0; i < actions.length(); i += 1) {
                            JSONObject action = actions.optJSONObject(i);
                            if (action == null) continue;
                            Log.i(TAG, "device_action poll execute " + summarizeDeviceAction(action));
                            results.put(executeDeviceAction(action));
                        }
                        if (results.length() <= 0) return;
                        JSONObject payload = new JSONObject();
                        payload.put("results", results);
                        Log.i(TAG, "device_actions poll posting results count=" + results.length() + " " + summarizeDeviceActionResults(results));
                        postJson("/miniapp-api/device-actions/done", payload);
                    } catch (Exception e) {
                        Log.w(TAG, "pollPendingDeviceActions failed", e);
                    } finally {
                        if (conn != null) conn.disconnect();
                    }
                });
    }

    private String encodeQueryValue(String value) throws Exception {
        return URLEncoder.encode(String.valueOf(value == null ? "" : value), "UTF-8");
    }

    private String buildRealtimeWebSocketUrl() throws Exception {
        String base = API_BASE.trim();
        String wsBase;
        if (base.startsWith("https://")) {
            wsBase = "wss://" + base.substring("https://".length());
        } else if (base.startsWith("http://")) {
            wsBase = "ws://" + base.substring("http://".length());
        } else {
            wsBase = "wss://" + base;
        }
        while (wsBase.endsWith("/")) {
            wsBase = wsBase.substring(0, wsBase.length() - 1);
        }
        StringBuilder url = new StringBuilder(wsBase)
                .append("/ws/device?device_id=")
                .append(encodeQueryValue(panelDeviceId))
                .append("&window_id=")
                .append(encodeQueryValue(SUMITALK_MAIN_WINDOW_ID));
        String lastKey = String.valueOf(prefs.getString(PREF_LAST_HISTORY_MESSAGE_KEY, "")).trim();
        if (!lastKey.isEmpty()) {
            url.append("&last_message_key=").append(encodeQueryValue(lastKey));
        }
        return url.toString();
    }

    private void ensureRealtimeWebSocket() {
        if (serviceStopping || panelToken.isEmpty() || panelDeviceId.isEmpty()) return;
        if (realtimeConnected || realtimeConnecting) return;
        try {
            if (realtimeClient == null) {
                realtimeClient =
                        new OkHttpClient.Builder()
                                .connectTimeout(10, TimeUnit.SECONDS)
                                .readTimeout(0, TimeUnit.SECONDS)
                                .pingInterval(25, TimeUnit.SECONDS)
                                .build();
            }
            Request request =
                    new Request.Builder()
                            .url(buildRealtimeWebSocketUrl())
                            .header("Authorization", "Bearer " + panelToken)
                            .build();
            realtimeConnecting = true;
            realtimeReconnectScheduled = false;
            realtimeSocket = realtimeClient.newWebSocket(request, new DeviceRealtimeWebSocketListener());
        } catch (Exception e) {
            realtimeConnecting = false;
            Log.w(TAG, "ensureRealtimeWebSocket failed", e);
            scheduleRealtimeReconnect();
        }
    }

    private void scheduleRealtimeReconnect() {
        if (serviceStopping || realtimeReconnectScheduled || panelToken.isEmpty()) return;
        realtimeReconnectScheduled = true;
        int attempt = Math.min(6, realtimeReconnectAttempts + 1);
        realtimeReconnectAttempts = attempt;
        long delay = Math.min(REALTIME_RECONNECT_MAX_MS, REALTIME_RECONNECT_BASE_MS * (1L << Math.min(5, attempt - 1)));
        mainHandler.postDelayed(
                () -> {
                    realtimeReconnectScheduled = false;
                    ensureRealtimeWebSocket();
                },
                delay);
    }

    private void closeRealtimeWebSocket(boolean shutdownClient) {
        realtimeConnected = false;
        realtimeConnecting = false;
        realtimeReconnectScheduled = false;
        WebSocket socket = realtimeSocket;
        realtimeSocket = null;
        if (socket != null) {
            try {
                socket.close(1000, "service_update");
            } catch (Exception ignored) {
            }
        }
        if (shutdownClient && realtimeClient != null) {
            try {
                realtimeClient.dispatcher().executorService().shutdown();
                realtimeClient.connectionPool().evictAll();
            } catch (Exception ignored) {
            }
            realtimeClient = null;
        }
    }

    private boolean sendRealtimeJson(JSONObject payload) {
        WebSocket socket = realtimeSocket;
        if (socket == null || payload == null) return false;
        try {
            return socket.send(payload.toString());
        } catch (Exception e) {
            Log.w(TAG, "sendRealtimeJson failed", e);
            return false;
        }
    }

    private void handleRealtimeTextMessage(String text) {
        try {
            JSONObject root = new JSONObject(String.valueOf(text == null ? "" : text));
            String type = String.valueOf(root.optString("type", "")).trim();
            if ("ready".equals(type)) {
                String latestKey = String.valueOf(root.optString("latest_message_key", "")).trim();
                if (!latestKey.isEmpty() && String.valueOf(prefs.getString(PREF_LAST_HISTORY_MESSAGE_KEY, "")).trim().isEmpty()) {
                    prefs.edit().putString(PREF_LAST_HISTORY_MESSAGE_KEY, latestKey).apply();
                }
                return;
            }
            if ("assistant_message".equals(type)) {
                handleRealtimeAssistantMessage(root.optJSONObject("message"));
                return;
            }
            if ("device_actions".equals(type)) {
                JSONArray actions = root.optJSONArray("actions");
                if (actions != null && actions.length() > 0) {
                    Log.i(TAG, "device_actions realtime received source=" + root.optString("source", "") + " count=" + actions.length() + " deviceId=" + panelDeviceId);
                    ioExecutor.execute(() -> handleRealtimeDeviceActions(actions));
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "handleRealtimeTextMessage failed", e);
        }
    }

    private void handleRealtimeAssistantMessage(JSONObject message) {
        if (message == null) return;
        String latestKey = String.valueOf(message.optString("key", "")).trim();
        String latestPreview = String.valueOf(message.optString("preview", "")).trim();
        if (latestPreview.isEmpty()) {
            latestPreview = messageContentToText(message.opt("content"));
        }
        if (latestKey.isEmpty() && !latestPreview.isEmpty()) {
            String id = String.valueOf(message.optString("id", "")).trim();
            String createdAt = String.valueOf(message.optString("createdAt", "")).trim();
            latestKey = !id.isEmpty() ? id : createdAt + "|" + latestPreview.hashCode();
        }
        if (latestKey.isEmpty() || latestPreview.isEmpty()) return;
        String previousKey = String.valueOf(prefs.getString(PREF_LAST_HISTORY_MESSAGE_KEY, "")).trim();
        if (latestKey.equals(previousKey)) return;
        prefs.edit().putString(PREF_LAST_HISTORY_MESSAGE_KEY, latestKey).apply();
        if (!prefs.getBoolean(PREF_APP_VISIBLE, false)) {
            showMessagePopup(latestPreview);
        }
    }

    private void handleRealtimeDeviceActions(JSONArray actions) {
        try {
            JSONArray results = new JSONArray();
            for (int i = 0; i < actions.length(); i += 1) {
                JSONObject action = actions.optJSONObject(i);
                if (action == null) continue;
                Log.i(TAG, "device_action realtime execute " + summarizeDeviceAction(action));
                results.put(executeDeviceAction(action));
            }
            if (results.length() <= 0) return;
            JSONObject payload = new JSONObject();
            payload.put("type", "device_action_results");
            payload.put("results", results);
            Log.i(TAG, "device_actions realtime posting results count=" + results.length() + " " + summarizeDeviceActionResults(results));
            if (!sendRealtimeJson(payload)) {
                Log.w(TAG, "device_actions realtime result send failed, falling back to HTTP");
                JSONObject httpPayload = new JSONObject();
                httpPayload.put("results", results);
                postJson("/miniapp-api/device-actions/done", httpPayload);
            }
        } catch (Exception e) {
            Log.w(TAG, "handleRealtimeDeviceActions failed", e);
        }
    }

    private JSONObject executeDeviceAction(JSONObject action) {
        JSONObject result = new JSONObject();
        String id = String.valueOf(action.optString("id", "")).trim();
        String type = String.valueOf(action.optString("type", "")).trim();
        try {
            result.put("id", id);
            JSONObject payload = action.optJSONObject("payload");
            Log.i(TAG, "device_action start id=" + id + " type=" + type + " payload=" + summarizeActionPayload(payload));
            if ("create_system_alarm".equals(type)) {
                JSONObject detail = createSystemAlarmFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            if ("create_calendar_event".equals(type)) {
                JSONObject detail = createCalendarEventFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            if ("show_choice_dialog".equals(type)) {
                JSONObject detail = showChoiceDialogFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            if ("show_system_notification".equals(type)) {
                JSONObject detail = showSystemNotificationFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            if ("voice_call_invite".equals(type)) {
                JSONObject detail = showVoiceCallInviteFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            if ("request_screen_check".equals(type)) {
                JSONObject detail = requestScreenCheckFromAction(payload == null ? new JSONObject() : payload);
                result.put("status", "done");
                result.put("detail", detail);
                Log.i(TAG, "device_action done id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result));
                return result;
            }
            result.put("status", "failed");
            result.put("error", "unknown_action");
            Log.w(TAG, "device_action failed id=" + id + " type=" + type + " error=unknown_action");
            return result;
        } catch (Exception e) {
            try {
                result.put("status", "failed");
                result.put("error", e.getMessage() == null ? String.valueOf(e) : e.getMessage());
            } catch (Exception ignored) {
            }
            Log.w(TAG, "device_action exception id=" + id + " type=" + type + " " + summarizeDeviceActionResult(result), e);
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
            Log.w(TAG, "choice_dialog overlay_permission_denied");
            throw new IllegalStateException("overlay_permission_denied");
        }
        final String title = String.valueOf(payload.optString("title", "渡")).trim();
        final String message = String.valueOf(payload.optString("message", "")).trim();
        if (message.isEmpty()) throw new IllegalArgumentException("message_empty");
        final String level = String.valueOf(payload.optString("level", "info")).trim();
        final boolean dismissible = payload.optBoolean("dismissible", true);
        final int timeoutSeconds = Math.max(30, Math.min(1800, payload.optInt("timeoutSeconds", 600)));
        Log.i(TAG, "choice_dialog start title=" + title + " level=" + level + " timeoutSeconds=" + timeoutSeconds + " messageLen=" + message.length());

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
                        Log.i(TAG, "choice_dialog ui_create title=" + title + " level=" + level);
                        AlertDialog dialog = new AlertDialog.Builder(this).create();
                        dialog.setView(
                                buildChoiceDialogView(
                                        title.isEmpty() ? "渡" : title,
                                        message,
                                        level,
                                        finalChoiceALabel,
                                        finalChoiceBLabel,
                                        timeoutSeconds,
                                        () -> {
                                            completeChoiceDialog(
                                                    resultRef,
                                                    latch,
                                                    buildChoiceDialogResult(finalChoiceAId, finalChoiceALabel, level, false, false));
                                            dismissChoiceDialog(dialogRef);
                                        },
                                        () -> {
                                            completeChoiceDialog(
                                                    resultRef,
                                                    latch,
                                                    buildChoiceDialogResult(finalChoiceBId, finalChoiceBLabel, level, false, false));
                                            dismissChoiceDialog(dialogRef);
                                        }),
                                0,
                                0,
                                0,
                                0);
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
                        Log.i(TAG, "choice_dialog shown title=" + title + " level=" + level);
                        android.view.Window shownWindow = dialog.getWindow();
                        if (shownWindow != null) {
                            shownWindow.setBackgroundDrawable(new ColorDrawable(Color.TRANSPARENT));
                            shownWindow.getDecorView().setPadding(0, 0, 0, 0);
                            WindowManager.LayoutParams attrs = shownWindow.getAttributes();
                            attrs.width = Math.min(getResources().getDisplayMetrics().widthPixels - dp(40), dp(360));
                            shownWindow.setAttributes(attrs);
                        }
                    } catch (Exception e) {
                        Log.w(TAG, "choice_dialog ui_failed title=" + title + " error=" + e.getMessage(), e);
                        completeChoiceDialog(resultRef, latch, buildChoiceDialogError(e));
                    }
                });
        if (!latch.await(timeoutSeconds, TimeUnit.SECONDS)) {
            Log.w(TAG, "choice_dialog timeout title=" + title + " timeoutSeconds=" + timeoutSeconds);
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
        Log.i(TAG, "choice_dialog result title=" + title + " " + summarizeDetail(detail));
        return detail;
    }

    private View buildChoiceDialogView(
            String title,
            String message,
            String level,
            String choiceALabel,
            String choiceBLabel,
            int timeoutSeconds,
            Runnable onChoiceA,
            Runnable onChoiceB) {
        FrameLayout wrapper = new FrameLayout(this);
        wrapper.setClipChildren(false);
        wrapper.setClipToPadding(false);
        wrapper.setPadding(0, dp(14), 0, 0);

        View leftEar = buildChoiceDialogEar(false);
        FrameLayout.LayoutParams leftEarParams =
                new FrameLayout.LayoutParams(dp(40), dp(40), Gravity.TOP | Gravity.START);
        leftEarParams.leftMargin = dp(56);
        wrapper.addView(leftEar, leftEarParams);

        View rightEar = buildChoiceDialogEar(true);
        FrameLayout.LayoutParams rightEarParams =
                new FrameLayout.LayoutParams(dp(40), dp(40), Gravity.TOP | Gravity.END);
        rightEarParams.rightMargin = dp(56);
        wrapper.addView(rightEar, rightEarParams);

        FrameLayout card = new FrameLayout(this);
        card.setBackground(choiceDialogCardBackground());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            card.setElevation(dp(18));
        }
        FrameLayout.LayoutParams cardParams =
                new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT);
        cardParams.topMargin = dp(14);
        wrapper.addView(card, cardParams);

        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setClipToPadding(false);
        card.addView(
                content,
                new FrameLayout.LayoutParams(
                        FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout topRow = new LinearLayout(this);
        topRow.setOrientation(LinearLayout.HORIZONTAL);
        topRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams topRowParams =
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        topRowParams.setMargins(dp(24), dp(24), dp(24), 0);
        content.addView(
                topRow,
                topRowParams);

        TextView badge = new TextView(this);
        badge.setText("✦  渡的确认");
        badge.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        badge.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        badge.setTextColor(choiceDialogBadgeTextColor(level));
        badge.setIncludeFontPadding(false);
        badge.setGravity(Gravity.CENTER);
        badge.setPadding(dp(10), dp(6), dp(10), dp(6));
        badge.setBackground(roundedChoiceDialogRect(choiceDialogAccentSoftColor(level), 999, 0x00000000, 0));
        topRow.addView(
                badge,
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        TextView timeout = new TextView(this);
        timeout.setText(formatChoiceDialogTimeout(timeoutSeconds));
        timeout.setTextSize(TypedValue.COMPLEX_UNIT_SP, 12);
        timeout.setTextColor(0xFFA6998E);
        timeout.setIncludeFontPadding(false);
        timeout.setGravity(Gravity.END | Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams timeoutParams =
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        timeoutParams.leftMargin = dp(12);
        topRow.addView(timeout, timeoutParams);

        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setOrientation(LinearLayout.HORIZONTAL);
        titleRow.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams titleRowParams =
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        titleRowParams.setMargins(dp(28), dp(24), dp(28), 0);
        content.addView(titleRow, titleRowParams);

        TextView titleView = new TextView(this);
        titleView.setText(title);
        titleView.setTextColor(0xFF4A4440);
        titleView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 21);
        titleView.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        titleView.setIncludeFontPadding(false);
        titleView.setLineSpacing(dp(2), 1.0f);
        titleRow.addView(
                titleView,
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        View titleDot = new View(this);
        titleDot.setBackground(roundedChoiceDialogRect(choiceDialogPrimaryEndColor(level), 999, 0x00000000, 0));
        LinearLayout.LayoutParams dotParams = new LinearLayout.LayoutParams(dp(8), dp(8));
        dotParams.leftMargin = dp(8);
        titleRow.addView(titleDot, dotParams);

        TextView messageView = new TextView(this);
        messageView.setText(message);
        messageView.setTextColor(0xFF635C56);
        messageView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        messageView.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        messageView.setLineSpacing(dp(5), 1.0f);
        messageView.setIncludeFontPadding(true);
        BoundedScrollView messageScroll = new BoundedScrollView(this, dp(320));
        messageScroll.setFillViewport(false);
        messageScroll.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);
        messageScroll.setVerticalScrollBarEnabled(false);
        messageScroll.addView(
                messageView,
                new ScrollView.LayoutParams(
                        ScrollView.LayoutParams.MATCH_PARENT, ScrollView.LayoutParams.WRAP_CONTENT));
        LinearLayout.LayoutParams messageParams =
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        messageParams.setMargins(dp(28), dp(12), dp(28), 0);
        content.addView(messageScroll, messageParams);

        LinearLayout buttonStack = new LinearLayout(this);
        buttonStack.setOrientation(LinearLayout.VERTICAL);
        LinearLayout.LayoutParams buttonStackParams =
                new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        buttonStackParams.setMargins(dp(24), dp(22), dp(24), 0);
        content.addView(buttonStack, buttonStackParams);

        Button primaryButton = buildChoiceDialogButton(choiceALabel, true, level);
        primaryButton.setOnClickListener(v -> onChoiceA.run());
        buttonStack.addView(primaryButton, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52)));

        Button secondaryButton = buildChoiceDialogButton(choiceBLabel, false, level);
        secondaryButton.setOnClickListener(v -> onChoiceB.run());
        LinearLayout.LayoutParams secondaryParams =
                new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(52));
        secondaryParams.topMargin = dp(12);
        buttonStack.addView(secondaryButton, secondaryParams);

        View handle = new View(this);
        handle.setBackground(roundedChoiceDialogRect(0x80E8E0D8, 999, 0x00000000, 0));
        LinearLayout.LayoutParams handleParams = new LinearLayout.LayoutParams(dp(32), dp(4));
        handleParams.gravity = Gravity.CENTER_HORIZONTAL;
        handleParams.setMargins(0, dp(16), 0, dp(12));
        content.addView(handle, handleParams);

        return wrapper;
    }

    private Button buildChoiceDialogButton(String label, boolean primary, String level) {
        Button button = new Button(this);
        button.setText(primary ? label + "  ›" : label);
        button.setAllCaps(false);
        button.setTextSize(TypedValue.COMPLEX_UNIT_SP, primary ? 16 : 15);
        button.setTypeface(Typeface.create("sans-serif", Typeface.BOLD));
        button.setGravity(Gravity.CENTER);
        button.setIncludeFontPadding(false);
        button.setMinHeight(0);
        button.setMinimumHeight(0);
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(dp(10), 0, dp(10), 0);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            button.setStateListAnimator(null);
        }
        if (primary) {
            button.setTextColor(Color.WHITE);
            button.setBackground(choiceDialogPrimaryBackground(level));
        } else {
            button.setTextColor(0xFF8B7E74);
            button.setBackground(roundedChoiceDialogRect(0xFFFDF2F0, 24, 0x00000000, 0));
        }
        return button;
    }

    private View buildChoiceDialogEar(boolean right) {
        View ear = new View(this);
        ear.setBackground(roundedChoiceDialogRect(0xFFFFF9F2, 12, 0x14D7B89A, 1));
        ear.setRotation(right ? 10f : -10f);
        return ear;
    }

    private GradientDrawable choiceDialogCardBackground() {
        GradientDrawable drawable =
                new GradientDrawable(
                        GradientDrawable.Orientation.TOP_BOTTOM,
                        new int[] {0xFFFFFFFF, 0xFFFFF9F2});
        drawable.setShape(GradientDrawable.RECTANGLE);
        drawable.setCornerRadius(dp(32));
        drawable.setStroke(dp(1), 0x80FFFFFF);
        return drawable;
    }

    private GradientDrawable choiceDialogPrimaryBackground(String level) {
        GradientDrawable drawable =
                new GradientDrawable(
                        GradientDrawable.Orientation.TL_BR,
                        new int[] {choiceDialogPrimaryStartColor(level), choiceDialogPrimaryEndColor(level)});
        drawable.setShape(GradientDrawable.RECTANGLE);
        drawable.setCornerRadius(dp(24));
        return drawable;
    }

    private GradientDrawable roundedChoiceDialogRect(int color, int radiusDp, int strokeColor, int strokeDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setShape(GradientDrawable.RECTANGLE);
        drawable.setColor(color);
        drawable.setCornerRadius(dp(radiusDp));
        if (strokeDp > 0) {
            drawable.setStroke(dp(strokeDp), strokeColor);
        }
        return drawable;
    }

    private int choiceDialogBadgeTextColor(String level) {
        String normalized = level == null ? "" : level.toLowerCase(Locale.US);
        if (normalized.contains("danger") || normalized.contains("error") || normalized.contains("critical")) {
            return 0xFF9B4545;
        }
        if (normalized.contains("warn")) {
            return 0xFF9A5A27;
        }
        if (normalized.contains("success")) {
            return 0xFF3F7A61;
        }
        return 0xFF8B5E3C;
    }

    private int choiceDialogAccentSoftColor(String level) {
        String normalized = level == null ? "" : level.toLowerCase(Locale.US);
        if (normalized.contains("danger") || normalized.contains("error") || normalized.contains("critical")) {
            return 0xFFFFECEB;
        }
        if (normalized.contains("warn")) {
            return 0xFFFFF0E3;
        }
        if (normalized.contains("success")) {
            return 0xFFEAF6F1;
        }
        return 0xFFFFF0E8;
    }

    private int choiceDialogPrimaryStartColor(String level) {
        String normalized = level == null ? "" : level.toLowerCase(Locale.US);
        if (normalized.contains("danger") || normalized.contains("error") || normalized.contains("critical")) {
            return 0xFFE45F5B;
        }
        if (normalized.contains("warn")) {
            return 0xFFFF9866;
        }
        if (normalized.contains("success")) {
            return 0xFF62A985;
        }
        return 0xFFFF9B9B;
    }

    private int choiceDialogPrimaryEndColor(String level) {
        String normalized = level == null ? "" : level.toLowerCase(Locale.US);
        if (normalized.contains("danger") || normalized.contains("error") || normalized.contains("critical")) {
            return 0xFFFF9B9B;
        }
        if (normalized.contains("warn")) {
            return 0xFFFFC071;
        }
        if (normalized.contains("success")) {
            return 0xFF91CFB1;
        }
        return 0xFFFFB4A2;
    }

    private String formatChoiceDialogTimeout(int timeoutSeconds) {
        if (timeoutSeconds >= 60) {
            int minutes = Math.max(1, Math.round(timeoutSeconds / 60f));
            return "约 " + minutes + " 分钟后自动收起";
        }
        return timeoutSeconds + " 秒后自动收起";
    }

    private void dismissChoiceDialog(AtomicReference<AlertDialog> dialogRef) {
        AlertDialog dialog = dialogRef.get();
        if (dialog == null) return;
        try {
            dialog.dismiss();
        } catch (Exception ignored) {
        }
    }

    private static final class BoundedScrollView extends ScrollView {
        private final int maxHeight;

        BoundedScrollView(Context context, int maxHeight) {
            super(context);
            this.maxHeight = maxHeight;
        }

        @Override
        protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
            int limitedHeight = MeasureSpec.makeMeasureSpec(maxHeight, MeasureSpec.AT_MOST);
            super.onMeasure(widthMeasureSpec, limitedHeight);
        }
    }

    private JSONObject requestScreenCheckFromAction(JSONObject payload) throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !android.provider.Settings.canDrawOverlays(this)) {
            Log.w(TAG, "screen_check overlay_permission_denied");
            throw new IllegalStateException("overlay_permission_denied");
        }
        String title = String.valueOf(payload.optString("title", "渡想查岗")).trim();
        if (title.isEmpty()) title = "渡想查岗";
        String message = String.valueOf(payload.optString("message", "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。")).trim();
        if (message.isEmpty()) message = "渡想看一眼你现在屏幕上在做什么。只有你同意后才会截图。";
        if (!message.contains("辅助功能") && !message.contains("不会跳转")) {
            message += "\n\n同意后会通过 SumiTalk 辅助功能截取当前屏幕，不会主动跳转应用；如果辅助功能没开，则不会截图。";
        }
        int timeoutSeconds = Math.max(30, Math.min(300, payload.optInt("timeoutSeconds", 120)));
        Log.i(TAG, "screen_check start title=" + title + " timeoutSeconds=" + timeoutSeconds + " messageLen=" + message.length());

        JSONObject dialogPayload = new JSONObject();
        dialogPayload.put("title", title);
        dialogPayload.put("message", message);
        dialogPayload.put("level", "warning");
        dialogPayload.put("dismissible", true);
        dialogPayload.put("timeoutSeconds", timeoutSeconds);
        JSONArray choices = new JSONArray();
        JSONObject approve = new JSONObject();
        approve.put("id", "approve");
        approve.put("label", "同意");
        JSONObject decline = new JSONObject();
        decline.put("id", "decline");
        decline.put("label", "拒绝");
        choices.put(approve);
        choices.put(decline);
        dialogPayload.put("choices", choices);

        Log.i(TAG, "screen_check confirm_dialog_before title=" + title + " timeoutSeconds=" + timeoutSeconds);
        JSONObject choice = showChoiceDialogFromAction(dialogPayload);
        Log.i(TAG, "screen_check confirm_dialog_result " + summarizeDetail(choice));
        String choiceId = String.valueOf(choice.optString("choice_id", "")).trim();
        if (!"approve".equals(choiceId)) {
            JSONObject detail = new JSONObject();
            detail.put("approved", false);
            detail.put("stage", "sumitalk_confirm");
            detail.put("choice_id", choiceId.isEmpty() ? "decline" : choiceId);
            detail.put("label", choice.optString("label", ""));
            detail.put("dismissed", choice.optBoolean("dismissed", false));
            detail.put("timeout", choice.optBoolean("timeout", false));
            return detail;
        }

        String requestId = "screen_check_" + System.currentTimeMillis();
        Log.i(TAG, "screen_check capture_prepare requestId=" + requestId);
        ScreenCaptureBridge.create(requestId);
        try {
            Thread.sleep(350L);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        if (!SumiAccessibilityService.requestScreenshot(requestId)) {
            Log.w(TAG, "screen_check accessibility_request_failed requestId=" + requestId);
            JSONObject detail = new JSONObject();
            detail.put("approved", false);
            detail.put("stage", "accessibility_screenshot");
            detail.put("error", "accessibility_service_unavailable");
            ScreenCaptureBridge.complete(requestId, detail);
        }

        JSONObject detail = ScreenCaptureBridge.await(requestId, Math.max(45L, timeoutSeconds) * 1000L);
        if (detail == null) {
            Log.w(TAG, "screen_check capture_timeout requestId=" + requestId + " timeoutSeconds=" + timeoutSeconds);
            detail = new JSONObject();
            detail.put("approved", false);
            detail.put("stage", "capture_wait");
            detail.put("reason", "capture_timeout");
            detail.put("timeout", true);
        }
        Log.i(TAG, "screen_check result requestId=" + requestId + " " + summarizeDetail(detail));
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

    private JSONObject showSystemNotificationFromAction(JSONObject payload) throws Exception {
        String title = String.valueOf(payload.optString("title", "SumiTalk")).trim();
        String message = String.valueOf(payload.optString("message", "")).trim();
        if (title.isEmpty()) title = "SumiTalk";
        if (message.isEmpty()) throw new IllegalArgumentException("message_empty");
        String level = String.valueOf(payload.optString("level", "info")).trim();
        String category = String.valueOf(payload.optString("category", "")).trim();
        boolean openApp = payload.optBoolean("openApp", true);
        boolean notified = showAppSystemNotification(title, message, level, category, openApp);
        JSONObject detail = new JSONObject();
        detail.put("notified", notified);
        detail.put("title", title);
        detail.put("openApp", openApp);
        return detail;
    }

    private JSONObject showVoiceCallInviteFromAction(JSONObject payload) throws Exception {
        String title = String.valueOf(payload.optString("title", "渡来电")).trim();
        String callerName = String.valueOf(payload.optString("callerName", "渡")).trim();
        String openingLine = String.valueOf(payload.optString("openingLine", "")).trim();
        String urgency = String.valueOf(payload.optString("urgency", "normal")).trim().toLowerCase(Locale.US);
        String callId = String.valueOf(payload.optString("callId", "")).trim();
        int timeoutSeconds = payload.optInt("timeoutSeconds", 180);
        if (title.isEmpty()) title = "渡来电";
        if (callerName.isEmpty()) callerName = "渡";
        if (openingLine.isEmpty()) throw new IllegalArgumentException("opening_line_empty");
        if (!"important".equals(urgency) && !"urgent".equals(urgency)) urgency = "normal";
        if (callId.isEmpty()) callId = "call_" + System.currentTimeMillis();
        timeoutSeconds = Math.max(30, Math.min(900, timeoutSeconds));

        JSONObject detail = new JSONObject();
        detail.put("callId", callId);
        detail.put("urgency", urgency);
        detail.put("timeoutSeconds", timeoutSeconds);
        if (!canPostNotifications()) {
            detail.put("notified", false);
            detail.put("error", "notification_permission_denied");
            Log.w(TAG, "voice call invite skipped: notification permission denied callId=" + callId);
            return detail;
        }

        JSONObject invite = new JSONObject(payload.toString());
        invite.put("title", title);
        invite.put("callerName", callerName);
        invite.put("openingLine", openingLine);
        invite.put("urgency", urgency);
        invite.put("callId", callId);
        invite.put("timeoutSeconds", timeoutSeconds);

        Intent openIntent = buildOpenVoiceCallIntent(invite);
        int requestCode = callId.hashCode() & 0x7fffffff;
        PendingIntent openPendingIntent =
                PendingIntent.getActivity(
                        this,
                        requestCode,
                        openIntent,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        NotificationCompat.Builder builder =
                new NotificationCompat.Builder(this, VOICE_CALL_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle(title)
                        .setContentText(callerName + "想和你语音")
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(openingLine))
                        .setContentIntent(openPendingIntent)
                        .addAction(R.mipmap.ic_launcher_round, "接听", openPendingIntent)
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_MAX)
                        .setDefaults(Notification.DEFAULT_ALL)
                        .setCategory(NotificationCompat.CATEGORY_CALL)
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .setWhen(System.currentTimeMillis())
                        .setShowWhen(true)
                        .setTimeoutAfter(timeoutSeconds * 1000L);
        if ("important".equals(urgency) || "urgent".equals(urgency)) {
            builder.setFullScreenIntent(openPendingIntent, true);
        }

        NotificationManagerCompat.from(this).notify(requestCode, builder.build());
        detail.put("notified", true);
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

    private boolean canPostNotifications() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
                || ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                        == PackageManager.PERMISSION_GRANTED;
    }

    private Intent buildOpenAppIntent() {
        Intent openIntent = getPackageManager().getLaunchIntentForPackage(getPackageName());
        if (openIntent == null) {
            openIntent = new Intent(this, MainActivity.class);
        }
        return openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
    }

    private Intent buildOpenVoiceCallIntent(JSONObject invite) {
        Intent openIntent = new Intent(this, MainActivity.class);
        openIntent.setAction(MainActivity.ACTION_OPEN_VOICE_CALL);
        openIntent.putExtra(MainActivity.EXTRA_VOICE_CALL_INVITE_JSON, invite.toString());
        return openIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
    }

    private String resolveNotificationCategory(String category, String level) {
        String raw = String.valueOf(category == null ? "" : category).trim().toLowerCase(Locale.US);
        if ("error".equals(raw)) return NotificationCompat.CATEGORY_ERROR;
        if ("event".equals(raw)) return NotificationCompat.CATEGORY_EVENT;
        if ("reminder".equals(raw)) return NotificationCompat.CATEGORY_REMINDER;
        if ("status".equals(raw)) return NotificationCompat.CATEGORY_STATUS;
        if ("message".equals(raw)) return NotificationCompat.CATEGORY_MESSAGE;
        String lv = String.valueOf(level == null ? "" : level).trim().toLowerCase(Locale.US);
        if ("error".equals(lv) || "warning".equals(lv)) return NotificationCompat.CATEGORY_ERROR;
        return NotificationCompat.CATEGORY_MESSAGE;
    }

    private boolean showAppSystemNotification(String title, String message, String level, String category, boolean openApp) {
        if (!canPostNotifications()) {
            Log.w(TAG, "system notification skipped: notification permission denied");
            return false;
        }
        NotificationCompat.Builder builder =
                new NotificationCompat.Builder(this, MESSAGE_CHANNEL_ID)
                        .setSmallIcon(R.mipmap.ic_launcher_round)
                        .setContentTitle(title)
                        .setContentText(message)
                        .setStyle(new NotificationCompat.BigTextStyle().bigText(message))
                        .setAutoCancel(true)
                        .setPriority(NotificationCompat.PRIORITY_HIGH)
                        .setDefaults(Notification.DEFAULT_ALL)
                        .setCategory(resolveNotificationCategory(category, level))
                        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
                        .setWhen(System.currentTimeMillis())
                        .setShowWhen(true);
        if (openApp) {
            PendingIntent pi =
                    PendingIntent.getActivity(
                            this,
                            (int) (System.currentTimeMillis() & 0x7fffffff),
                            buildOpenAppIntent(),
                            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            builder.setContentIntent(pi);
        }
        NotificationManagerCompat.from(this)
                .notify((int) (System.currentTimeMillis() & 0x7fffffff), builder.build());
        return true;
    }

    private void showCalendarEventCreatedNotification(long eventId, long startMillis, String title) {
        if (!canPostNotifications()) {
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
        if (!canPostNotifications()) {
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
        Log.i(TAG, "message overlay bubble disabled");
    }

    private String summarizeDeviceAction(JSONObject action) {
        if (action == null) return "action=null";
        JSONObject payload = action.optJSONObject("payload");
        return "id="
                + String.valueOf(action.optString("id", "")).trim()
                + " type="
                + String.valueOf(action.optString("type", "")).trim()
                + " payload="
                + summarizeActionPayload(payload);
    }

    private String summarizeActionPayload(JSONObject payload) {
        if (payload == null) return "{}";
        String title = String.valueOf(payload.optString("title", "")).trim();
        String message = String.valueOf(payload.optString("message", payload.optString("content", ""))).trim();
        JSONArray choices = payload.optJSONArray("choices");
        return "{title="
                + title
                + ", messageLen="
                + message.length()
                + ", timeoutSeconds="
                + payload.optString("timeoutSeconds", "")
                + ", choices="
                + (choices == null ? 0 : choices.length())
                + "}";
    }

    private String summarizeDetail(JSONObject detail) {
        if (detail == null) return "{}";
        StringBuilder sb = new StringBuilder("{");
        appendSummaryField(sb, "stage", detail.optString("stage", ""));
        appendSummaryField(sb, "approved", detail.has("approved") ? String.valueOf(detail.optBoolean("approved")) : "");
        appendSummaryField(sb, "choice_id", detail.optString("choice_id", ""));
        appendSummaryField(sb, "dismissed", detail.has("dismissed") ? String.valueOf(detail.optBoolean("dismissed")) : "");
        appendSummaryField(sb, "timeout", detail.has("timeout") ? String.valueOf(detail.optBoolean("timeout")) : "");
        appendSummaryField(sb, "reason", detail.optString("reason", ""));
        appendSummaryField(sb, "error", detail.optString("error", ""));
        appendSummaryField(sb, "image_url", detail.optString("image_url", "").isEmpty() ? "" : "present");
        sb.append("}");
        return sb.toString();
    }

    private String summarizeDeviceActionResult(JSONObject result) {
        if (result == null) return "{}";
        JSONObject detail = result.optJSONObject("detail");
        return "{status="
                + result.optString("status", "")
                + ", error="
                + result.optString("error", "")
                + ", detail="
                + summarizeDetail(detail)
                + "}";
    }

    private String summarizeDeviceActionResults(JSONArray results) {
        if (results == null) return "[]";
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < results.length(); i += 1) {
            JSONObject row = results.optJSONObject(i);
            if (row == null) continue;
            if (sb.length() > 1) sb.append(", ");
            sb.append(row.optString("id", ""))
                    .append(":")
                    .append(row.optString("status", ""))
                    .append("/")
                    .append(summarizeDetail(row.optJSONObject("detail")));
        }
        sb.append("]");
        return sb.toString();
    }

    private void appendSummaryField(StringBuilder sb, String key, String value) {
        String raw = String.valueOf(value == null ? "" : value).trim();
        if (raw.isEmpty()) return;
        if (raw.length() > 80) raw = raw.substring(0, 80);
        if (sb.length() > 1) sb.append(", ");
        sb.append(key).append("=").append(raw);
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
                String errorBody = "";
                InputStream errorStream = conn.getErrorStream();
                if (errorStream != null) {
                    errorBody = readAllText(errorStream);
                }
                Log.w(TAG, "postJson non-2xx " + path + " code=" + code + " body=" + errorBody);
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

    private final class DeviceRealtimeWebSocketListener extends WebSocketListener {
        @Override
        public void onOpen(WebSocket webSocket, Response response) {
            realtimeSocket = webSocket;
            realtimeConnected = true;
            realtimeConnecting = false;
            realtimeReconnectAttempts = 0;
            realtimeReconnectScheduled = false;
            Log.i(TAG, "realtime websocket connected");
        }

        @Override
        public void onMessage(WebSocket webSocket, String text) {
            handleRealtimeTextMessage(text);
        }

        @Override
        public void onClosed(WebSocket webSocket, int code, String reason) {
            if (webSocket == realtimeSocket) {
                realtimeSocket = null;
            }
            realtimeConnected = false;
            realtimeConnecting = false;
            Log.i(TAG, "realtime websocket closed code=" + code + " reason=" + reason);
            scheduleRealtimeReconnect();
        }

        @Override
        public void onFailure(WebSocket webSocket, Throwable t, Response response) {
            if (webSocket == realtimeSocket) {
                realtimeSocket = null;
            }
            realtimeConnected = false;
            realtimeConnecting = false;
            String status = response == null ? "" : (" status=" + response.code());
            Log.w(TAG, "realtime websocket failed" + status, t);
            scheduleRealtimeReconnect();
        }
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
