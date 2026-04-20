package com.sumitalk.app;

import android.content.Context;
import android.content.Intent;
import androidx.core.content.ContextCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "SumiOverlay")
public class OverlayControlPlugin extends Plugin {

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
}
