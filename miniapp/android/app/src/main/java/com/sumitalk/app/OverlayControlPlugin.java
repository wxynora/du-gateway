package com.sumitalk.app;

import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.provider.Settings;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.util.UUID;

@CapacitorPlugin(name = "SumiOverlay")
public class OverlayControlPlugin extends Plugin {
    private static final String PREF_NATIVE_DEVICE = "native_device_id";

    @PluginMethod
    public void setFloatingBallEnabled(PluginCall call) {
        boolean enabled = call.getBoolean("enabled", true);
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                .edit()
                .putBoolean(FloatingBallService.PREF_OVERLAY_VISIBLE, enabled)
                .apply();
        Intent intent = new Intent(ctx, FloatingBallService.class);
        intent.setAction(FloatingBallService.ACTION_START_OR_UPDATE);
        ContextCompat.startForegroundService(ctx, intent);
        call.resolve();
    }

    @PluginMethod
    public void getFloatingBallEnabled(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        boolean enabled =
                ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE)
                        .getBoolean(FloatingBallService.PREF_OVERLAY_VISIBLE, true);
        JSObject o = new JSObject();
        o.put("enabled", enabled);
        call.resolve(o);
    }

    @PluginMethod
    public void getStableDeviceId(PluginCall call) {
        Context ctx = getContext();
        if (ctx == null) {
            call.reject("no_context");
            return;
        }
        JSObject o = new JSObject();
        o.put("deviceId", resolveStableDeviceId(ctx));
        call.resolve(o);
    }

    private String resolveStableDeviceId(Context ctx) {
        try {
            String androidId =
                    String.valueOf(Settings.Secure.getString(ctx.getContentResolver(), Settings.Secure.ANDROID_ID))
                            .trim();
            if (!androidId.isEmpty() && !"9774d56d682e549c".equals(androidId)) {
                return "android_" + androidId.toLowerCase();
            }
        } catch (Exception ignored) {
        }

        SharedPreferences sp = ctx.getSharedPreferences(FloatingBallService.PREFS_NAME, Context.MODE_PRIVATE);
        String existing = String.valueOf(sp.getString(PREF_NATIVE_DEVICE, "")).trim();
        if (!existing.isEmpty()) {
            return existing;
        }
        String next = "native_" + UUID.randomUUID().toString().replace("-", "");
        sp.edit().putString(PREF_NATIVE_DEVICE, next).apply();
        return next;
    }
}
