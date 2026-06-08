package com.sumitalk.app;

import android.content.Context;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.sumitalk.app.chat.SumiChatStore;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.json.JSONArray;
import org.json.JSONObject;

@CapacitorPlugin(name = "SumiChatStore")
public class SumiChatStorePlugin extends Plugin {
    private final ExecutorService dbExecutor = Executors.newSingleThreadExecutor();
    private SumiChatStore store;

    @Override
    public void load() {
        Context ctx = getContext();
        if (ctx != null) {
            store = new SumiChatStore(ctx);
        }
    }

    @PluginMethod
    public void getStatus(PluginCall call) {
        run(call, () -> {
            JSONObject status = getStore().status();
            JSObject out = new JSObject();
            out.put("ok", status.optBoolean("ok", false));
            out.put("schemaVersion", status.optInt("schemaVersion", 1));
            call.resolve(out);
        });
    }

    @PluginMethod
    public void upsertMessages(PluginCall call) {
        run(call, () -> {
            String deviceId = call.getString("deviceId", "");
            String windowId = call.getString("windowId", "");
            JSONArray messages = call.getData().optJSONArray("messages");
            getStore().upsertMessages(deviceId, windowId, messages == null ? new JSONArray() : messages);
            call.resolve();
        });
    }

    @PluginMethod
    public void listMessages(PluginCall call) {
        run(call, () -> {
            String deviceId = call.getString("deviceId", "");
            String windowId = call.getString("windowId", "");
            Integer limitValue = call.getInt("limit");
            int limit = limitValue == null ? 200 : limitValue;
            String before = call.getString("before", "");
            JSObject out = new JSObject();
            out.put("messages", getStore().listMessages(deviceId, windowId, limit, before));
            call.resolve(out);
        });
    }

    @PluginMethod
    public void listHistoryRows(PluginCall call) {
        run(call, () -> {
            JSONArray windowIds = call.getData().optJSONArray("windowIds");
            JSObject out = new JSObject();
            out.put("rows", getStore().listHistoryRows(windowIds == null ? new JSONArray() : windowIds));
            call.resolve(out);
        });
    }

    @PluginMethod
    public void inspectRows(PluginCall call) {
        run(call, () -> {
            JSObject out = new JSObject();
            out.put("rows", getStore().inspectRows());
            call.resolve(out);
        });
    }

    @PluginMethod
    public void latestMessages(PluginCall call) {
        run(call, () -> {
            String deviceId = call.getString("deviceId", "");
            JSObject out = new JSObject();
            out.put("messages", getStore().latestMessages(deviceId));
            call.resolve(out);
        });
    }

    @PluginMethod
    public void migrateDevice(PluginCall call) {
        run(call, () -> {
            String oldDeviceId = call.getString("oldDeviceId", "");
            String newDeviceId = call.getString("newDeviceId", "");
            getStore().migrateDevice(oldDeviceId, newDeviceId);
            call.resolve();
        });
    }

    @PluginMethod
    public void setMeta(PluginCall call) {
        run(call, () -> {
            getStore().setMeta(call.getString("key", ""), call.getString("value", ""));
            call.resolve();
        });
    }

    @PluginMethod
    public void getMeta(PluginCall call) {
        run(call, () -> {
            JSObject out = new JSObject();
            out.put("value", getStore().getMeta(call.getString("key", "")));
            call.resolve(out);
        });
    }

    @PluginMethod
    public void createDraftTurn(PluginCall call) {
        run(call, () -> {
            String deviceId = call.getString("deviceId", "");
            String windowId = call.getString("windowId", "");
            JSONObject userMessage = call.getData().optJSONObject("userMessage");
            JSONObject assistantMessage = call.getData().optJSONObject("assistantMessage");
            JSONObject operation = call.getData().optJSONObject("operation");
            JSONObject result = getStore().createDraftTurn(deviceId, windowId, userMessage, assistantMessage, operation);
            JSObject out = new JSObject();
            if (result != null && result.optJSONObject("operation") != null) {
                out.put("operation", result.optJSONObject("operation"));
            }
            call.resolve(out);
        });
    }

    @PluginMethod
    public void attachJob(PluginCall call) {
        run(call, () -> {
            getStore().attachJob(call.getString("operationId", ""), call.getString("jobId", ""));
            call.resolve();
        });
    }

    @PluginMethod
    public void completeOperation(PluginCall call) {
        run(call, () -> {
            getStore().completeOperation(
                    call.getString("operationId", ""),
                    call.getData().optJSONObject("assistantMessage")
            );
            call.resolve();
        });
    }

    @PluginMethod
    public void failOperation(PluginCall call) {
        run(call, () -> {
            getStore().failOperation(
                    call.getString("operationId", ""),
                    call.getString("error", ""),
                    call.getData().optJSONObject("assistantMessage")
            );
            call.resolve();
        });
    }

    @PluginMethod
    public void getOperation(PluginCall call) {
        run(call, () -> {
            JSObject out = new JSObject();
            JSONObject operation = getStore().getOperation(call.getString("operationId", ""));
            if (operation != null) out.put("operation", operation);
            call.resolve(out);
        });
    }

    @PluginMethod
    public void listActiveOperations(PluginCall call) {
        run(call, () -> {
            JSObject out = new JSObject();
            out.put("operations", getStore().listActiveOperations(call.getString("deviceId", ""), call.getString("windowId", "")));
            call.resolve(out);
        });
    }

    private SumiChatStore getStore() throws Exception {
        if (store != null) return store;
        Context ctx = getContext();
        if (ctx == null) throw new IllegalStateException("no_context");
        store = new SumiChatStore(ctx);
        return store;
    }

    private void run(PluginCall call, ThrowingRunnable action) {
        dbExecutor.execute(() -> {
            try {
                action.run();
            } catch (Exception e) {
                call.reject(e.getMessage() == null ? e.toString() : e.getMessage(), e);
            }
        });
    }

    private interface ThrowingRunnable {
        void run() throws Exception;
    }
}
