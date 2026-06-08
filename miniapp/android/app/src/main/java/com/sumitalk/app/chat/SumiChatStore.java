package com.sumitalk.app.chat;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import org.json.JSONArray;
import org.json.JSONObject;

public class SumiChatStore {
    private final SumiChatDatabase database;

    public SumiChatStore(Context context) {
        this.database = new SumiChatDatabase(context.getApplicationContext());
    }

    public JSONObject status() throws Exception {
        SQLiteDatabase db = database.getReadableDatabase();
        JSONObject out = new JSONObject();
        out.put("ok", true);
        out.put("schemaVersion", db.getVersion());
        return out;
    }

    public void upsertMessages(String deviceId, String windowId, JSONArray messages) throws Exception {
        String did = safe(deviceId);
        String wid = safe(windowId);
        if (did.isEmpty() || wid.isEmpty() || messages == null) return;
        SQLiteDatabase db = database.getWritableDatabase();
        db.beginTransaction();
        try {
            String now = nowIso();
            for (int i = 0; i < messages.length(); i += 1) {
                JSONObject msg = messages.optJSONObject(i);
                if (msg == null) continue;
                String id = safe(msg.optString("id"));
                String role = safe(msg.optString("role")).toLowerCase();
                String content = text(msg.optString("content"));
                String status = safe(msg.optString("status", "sent"));
                if (id.isEmpty() || role.isEmpty()) continue;
                if (content.trim().isEmpty() && !("assistant".equals(role) && "pending".equals(status))) continue;
                db.insertWithOnConflict("chat_messages", null, valuesFromMessage(did, wid, msg, now), SQLiteDatabase.CONFLICT_REPLACE);
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public JSONArray listMessages(String deviceId, String windowId, int limit, String before) throws Exception {
        String did = safe(deviceId);
        String wid = safe(windowId);
        JSONArray out = new JSONArray();
        if (did.isEmpty() || wid.isEmpty()) return out;
        int safeLimit = Math.max(1, Math.min(limit <= 0 ? 200 : limit, 1000));
        String where = "device_id=? AND window_id=? AND (deleted_at IS NULL OR deleted_at='')";
        String[] args;
        String beforeValue = safe(before);
        if (!beforeValue.isEmpty()) {
            where += " AND created_at < ?";
            args = new String[]{did, wid, beforeValue};
        } else {
            args = new String[]{did, wid};
        }
        SQLiteDatabase db = database.getReadableDatabase();
        JSONArray desc = new JSONArray();
        try (Cursor c = db.query(
                "chat_messages",
                null,
                where,
                args,
                null,
                null,
                "created_at DESC, id DESC",
                String.valueOf(safeLimit)
        )) {
            while (c.moveToNext()) {
                desc.put(messageFromCursor(c));
            }
        }
        for (int i = desc.length() - 1; i >= 0; i -= 1) {
            out.put(desc.getJSONObject(i));
        }
        return out;
    }

    public JSONArray listHistoryRows(JSONArray windowIds) throws Exception {
        JSONArray out = new JSONArray();
        if (windowIds == null || windowIds.length() == 0) return out;
        SQLiteDatabase db = database.getReadableDatabase();
        StringBuilder placeholders = new StringBuilder();
        String[] args = new String[windowIds.length()];
        for (int i = 0; i < windowIds.length(); i += 1) {
            if (i > 0) placeholders.append(",");
            placeholders.append("?");
            args[i] = safe(windowIds.optString(i));
        }
        String sql = "SELECT device_id, window_id, MAX(updated_at) AS updated_at, COUNT(*) AS count "
                + "FROM chat_messages WHERE window_id IN (" + placeholders + ") "
                + "AND (deleted_at IS NULL OR deleted_at='') GROUP BY device_id, window_id "
                + "ORDER BY updated_at DESC";
        try (Cursor c = db.rawQuery(sql, args)) {
            while (c.moveToNext()) {
                String did = c.getString(c.getColumnIndexOrThrow("device_id"));
                String wid = c.getString(c.getColumnIndexOrThrow("window_id"));
                JSONObject row = new JSONObject();
                row.put("key", did + "::" + wid);
                row.put("deviceId", did);
                row.put("windowId", wid);
                row.put("updatedAt", c.getString(c.getColumnIndexOrThrow("updated_at")));
                row.put("count", c.getInt(c.getColumnIndexOrThrow("count")));
                row.put("messages", listMessages(did, wid, 1000, ""));
                out.put(row);
            }
        }
        return out;
    }

    public JSONArray inspectRows() throws Exception {
        JSONArray out = new JSONArray();
        SQLiteDatabase db = database.getReadableDatabase();
        String sql = "SELECT device_id, window_id, MAX(updated_at) AS updated_at, COUNT(*) AS count "
                + "FROM chat_messages WHERE (deleted_at IS NULL OR deleted_at='') "
                + "GROUP BY device_id, window_id ORDER BY updated_at DESC";
        try (Cursor c = db.rawQuery(sql, null)) {
            while (c.moveToNext()) {
                String did = c.getString(c.getColumnIndexOrThrow("device_id"));
                String wid = c.getString(c.getColumnIndexOrThrow("window_id"));
                JSONObject row = new JSONObject();
                row.put("key", did + "::" + wid);
                row.put("deviceId", did);
                row.put("windowId", wid);
                row.put("updatedAt", c.getString(c.getColumnIndexOrThrow("updated_at")));
                row.put("count", c.getInt(c.getColumnIndexOrThrow("count")));
                out.put(row);
            }
        }
        return out;
    }

    public JSONArray latestMessages(String deviceId) throws Exception {
        String did = safe(deviceId);
        if (did.isEmpty()) return new JSONArray();
        SQLiteDatabase db = database.getReadableDatabase();
        String latestWindow = "";
        try (Cursor c = db.rawQuery(
                "SELECT window_id FROM chat_messages WHERE device_id=? AND (deleted_at IS NULL OR deleted_at='') ORDER BY updated_at DESC LIMIT 1",
                new String[]{did}
        )) {
            if (c.moveToNext()) latestWindow = safe(c.getString(0));
        }
        if (latestWindow.isEmpty()) return new JSONArray();
        return listMessages(did, latestWindow, 1000, "");
    }

    public void migrateDevice(String oldDeviceId, String newDeviceId) throws Exception {
        String oldId = safe(oldDeviceId);
        String newId = safe(newDeviceId);
        if (oldId.isEmpty() || newId.isEmpty() || oldId.equals(newId)) return;
        SQLiteDatabase db = database.getWritableDatabase();
        db.beginTransaction();
        try {
            JSONArray rows = new JSONArray();
            try (Cursor c = db.query(
                    "chat_messages",
                    null,
                    "device_id=?",
                    new String[]{oldId},
                    null,
                    null,
                    null
            )) {
                while (c.moveToNext()) rows.put(messageFromCursor(c));
            }
            for (int i = 0; i < rows.length(); i += 1) {
                JSONObject msg = rows.getJSONObject(i);
                String wid = safe(msg.optString("windowId"));
                String id = safe(msg.optString("id"));
                db.insertWithOnConflict("chat_messages", null, valuesFromMessage(newId, wid, msg, nowIso()), SQLiteDatabase.CONFLICT_REPLACE);
                db.delete("chat_messages", "message_key=?", new String[]{messageKey(oldId, wid, id)});
            }
            ContentValues opValues = new ContentValues();
            opValues.put("device_id", newId);
            db.update("chat_operations", opValues, "device_id=?", new String[]{oldId});
            ContentValues targetValues = new ContentValues();
            targetValues.put("reply_target", newId);
            db.update("chat_operations", targetValues, "reply_target=?", new String[]{oldId});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public JSONObject createDraftTurn(String deviceId, String windowId, JSONObject userMessage, JSONObject assistantMessage, JSONObject operation) throws Exception {
        String did = safe(deviceId);
        String wid = safe(windowId);
        JSONObject out = new JSONObject();
        if (did.isEmpty() || wid.isEmpty() || operation == null) return out;
        SQLiteDatabase db = database.getWritableDatabase();
        JSONObject stored = null;
        db.beginTransaction();
        try {
            String opId = safe(operation.optString("id"));
            String clientRequestId = safe(operation.optString("clientRequestId", operation.optString("client_request_id", "")));
            String replyTarget = safe(operation.optString("replyTarget", operation.optString("reply_target", did)));
            if (!clientRequestId.isEmpty()) {
                stored = getOperationByClientLocked(db, clientRequestId, wid, replyTarget);
            }
            if (stored == null && !opId.isEmpty()) {
                stored = getOperationByIdLocked(db, opId);
            }
            if (stored == null && !opId.isEmpty() && userMessage != null && assistantMessage != null) {
                String now = nowIso();
                db.insertWithOnConflict("chat_messages", null, valuesFromMessage(did, wid, userMessage, now), SQLiteDatabase.CONFLICT_REPLACE);
                db.insertWithOnConflict("chat_messages", null, valuesFromMessage(did, wid, assistantMessage, now), SQLiteDatabase.CONFLICT_REPLACE);
                db.insertWithOnConflict("chat_operations", null, valuesFromOperation(did, wid, operation, now), SQLiteDatabase.CONFLICT_REPLACE);
                stored = getOperationByIdLocked(db, opId);
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
        if (stored != null) out.put("operation", stored);
        return out;
    }

    public void attachJob(String operationId, String jobId) throws Exception {
        String opId = safe(operationId);
        String jid = safe(jobId);
        if (opId.isEmpty() || jid.isEmpty()) return;
        SQLiteDatabase db = database.getWritableDatabase();
        db.beginTransaction();
        try {
            JSONObject op = getOperationByIdLocked(db, opId);
            if (op == null) return;
            String now = nowIso();
            ContentValues opValues = new ContentValues();
            opValues.put("job_id", jid);
            opValues.put("status", "running");
            opValues.put("updated_at", now);
            opValues.put("last_attempt_at", now);
            opValues.put("retry_count", op.optInt("retryCount", 0) + 1);
            db.update("chat_operations", opValues, "id=?", new String[]{opId});

            String did = safe(op.optString("deviceId"));
            String wid = safe(op.optString("windowId"));
            String assistantId = safe(op.optString("assistantMessageId"));
            if (!did.isEmpty() && !wid.isEmpty() && !assistantId.isEmpty()) {
                ContentValues msgValues = new ContentValues();
                msgValues.put("job_id", jid);
                msgValues.put("status", "pending");
                msgValues.put("operation_id", opId);
                msgValues.put("updated_at", now);
                db.update("chat_messages", msgValues, "message_key=?", new String[]{messageKey(did, wid, assistantId)});
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public void completeOperation(String operationId, JSONObject assistantMessage) throws Exception {
        patchOperationTerminal(operationId, "done", "", assistantMessage);
    }

    public void failOperation(String operationId, String error, JSONObject assistantMessage) throws Exception {
        patchOperationTerminal(operationId, "failed", safe(error), assistantMessage);
    }

    public JSONObject getOperation(String operationId) throws Exception {
        String opId = safe(operationId);
        if (opId.isEmpty()) return null;
        return getOperationByIdLocked(database.getReadableDatabase(), opId);
    }

    public JSONArray listActiveOperations(String deviceId, String windowId) throws Exception {
        String did = safe(deviceId);
        String wid = safe(windowId);
        JSONArray out = new JSONArray();
        if (did.isEmpty()) return out;
        String where = "device_id=? AND status IN ('draft','posting','running')";
        String[] args;
        if (!wid.isEmpty()) {
            where += " AND window_id=?";
            args = new String[]{did, wid};
        } else {
            args = new String[]{did};
        }
        try (Cursor c = database.getReadableDatabase().query(
                "chat_operations",
                null,
                where,
                args,
                null,
                null,
                "updated_at ASC, created_at ASC",
                "50"
        )) {
            while (c.moveToNext()) {
                out.put(operationFromCursor(c));
            }
        }
        return out;
    }

    public void setMeta(String key, String value) throws Exception {
        String skey = safe(key);
        if (skey.isEmpty()) return;
        ContentValues values = new ContentValues();
        values.put("key", skey);
        values.put("value", safe(value));
        values.put("updated_at", nowIso());
        database.getWritableDatabase().insertWithOnConflict("chat_meta", null, values, SQLiteDatabase.CONFLICT_REPLACE);
    }

    public String getMeta(String key) throws Exception {
        String skey = safe(key);
        if (skey.isEmpty()) return "";
        try (Cursor c = database.getReadableDatabase().query(
                "chat_meta",
                new String[]{"value"},
                "key=?",
                new String[]{skey},
                null,
                null,
                null,
                "1"
        )) {
            if (c.moveToNext()) return safe(c.getString(0));
        }
        return "";
    }

    private JSONObject messageFromCursor(Cursor c) throws Exception {
        JSONObject out = new JSONObject();
        out.put("id", c.getString(c.getColumnIndexOrThrow("id")));
        out.put("deviceId", c.getString(c.getColumnIndexOrThrow("device_id")));
        out.put("windowId", c.getString(c.getColumnIndexOrThrow("window_id")));
        out.put("displayWindowId", c.getString(c.getColumnIndexOrThrow("display_window_id")));
        out.put("role", c.getString(c.getColumnIndexOrThrow("role")));
        out.put("content", c.getString(c.getColumnIndexOrThrow("content")));
        out.put("createdAt", c.getString(c.getColumnIndexOrThrow("created_at")));
        out.put("updatedAt", c.getString(c.getColumnIndexOrThrow("updated_at")));
        putOptional(out, "status", c.getString(c.getColumnIndexOrThrow("status")));
        putOptional(out, "clientRequestId", c.getString(c.getColumnIndexOrThrow("client_request_id")));
        putOptional(out, "operationId", c.getString(c.getColumnIndexOrThrow("operation_id")));
        putOptional(out, "jobId", c.getString(c.getColumnIndexOrThrow("job_id")));
        putOptional(out, "reasoning", c.getString(c.getColumnIndexOrThrow("reasoning")));
        String tokenJson = safe(c.getString(c.getColumnIndexOrThrow("token_count_json")));
        if (!tokenJson.isEmpty()) {
            try {
                out.put("tokenCount", new JSONObject(tokenJson));
            } catch (Exception ignored) {
            }
        }
        putOptional(out, "remoteKey", c.getString(c.getColumnIndexOrThrow("remote_key")));
        out.put("localRevision", c.getInt(c.getColumnIndexOrThrow("local_revision")));
        putOptional(out, "deletedAt", c.getString(c.getColumnIndexOrThrow("deleted_at")));
        return out;
    }

    private void patchOperationTerminal(String operationId, String status, String error, JSONObject assistantMessage) throws Exception {
        String opId = safe(operationId);
        if (opId.isEmpty()) return;
        SQLiteDatabase db = database.getWritableDatabase();
        db.beginTransaction();
        try {
            JSONObject op = getOperationByIdLocked(db, opId);
            if (op == null) return;
            String now = nowIso();
            String did = safe(op.optString("deviceId"));
            String wid = safe(op.optString("windowId"));
            String assistantId = safe(op.optString("assistantMessageId"));
            if (assistantMessage != null && !did.isEmpty() && !wid.isEmpty() && !assistantId.isEmpty()) {
                JSONObject msg = messageByKeyLocked(db, did, wid, assistantId);
                if (msg == null) msg = new JSONObject();
                msg.put("id", assistantId);
                msg.put("role", "assistant");
                msg.put("content", text(assistantMessage.optString("content", msg.optString("content", ""))));
                msg.put("createdAt", safe(msg.optString("createdAt", assistantMessage.optString("createdAt", now))));
                msg.put("updatedAt", now);
                msg.put("status", "done".equals(status) ? "sent" : "failed");
                msg.put("clientRequestId", safe(op.optString("clientRequestId")));
                msg.put("operationId", opId);
                msg.put("jobId", safe(assistantMessage.optString("jobId", op.optString("jobId", ""))));
                putOptional(msg, "reasoning", text(assistantMessage.optString("reasoning", "")));
                JSONObject tokenCount = assistantMessage.optJSONObject("tokenCount");
                if (tokenCount != null) msg.put("tokenCount", tokenCount);
                db.insertWithOnConflict("chat_messages", null, valuesFromMessage(did, wid, msg, now), SQLiteDatabase.CONFLICT_REPLACE);
            }

            ContentValues opValues = new ContentValues();
            opValues.put("status", status);
            opValues.put("error", error);
            opValues.put("updated_at", now);
            if (assistantMessage != null) {
                String jid = safe(assistantMessage.optString("jobId", op.optString("jobId", "")));
                if (!jid.isEmpty()) opValues.put("job_id", jid);
            }
            db.update("chat_operations", opValues, "id=?", new String[]{opId});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    private JSONObject messageByKeyLocked(SQLiteDatabase db, String deviceId, String windowId, String messageId) throws Exception {
        try (Cursor c = db.query(
                "chat_messages",
                null,
                "message_key=?",
                new String[]{messageKey(deviceId, windowId, messageId)},
                null,
                null,
                null,
                "1"
        )) {
            if (c.moveToNext()) return messageFromCursor(c);
        }
        return null;
    }

    private JSONObject getOperationByIdLocked(SQLiteDatabase db, String operationId) throws Exception {
        String opId = safe(operationId);
        if (opId.isEmpty()) return null;
        try (Cursor c = db.query(
                "chat_operations",
                null,
                "id=?",
                new String[]{opId},
                null,
                null,
                null,
                "1"
        )) {
            if (c.moveToNext()) return operationFromCursor(c);
        }
        return null;
    }

    private JSONObject getOperationByClientLocked(SQLiteDatabase db, String clientRequestId, String windowId, String replyTarget) throws Exception {
        String cid = safe(clientRequestId);
        String wid = safe(windowId);
        String target = safe(replyTarget);
        if (cid.isEmpty() || wid.isEmpty() || target.isEmpty()) return null;
        try (Cursor c = db.query(
                "chat_operations",
                null,
                "client_request_id=? AND window_id=? AND reply_target=?",
                new String[]{cid, wid, target},
                null,
                null,
                "updated_at DESC",
                "1"
        )) {
            if (c.moveToNext()) return operationFromCursor(c);
        }
        return null;
    }

    private JSONObject operationFromCursor(Cursor c) throws Exception {
        JSONObject out = new JSONObject();
        out.put("id", c.getString(c.getColumnIndexOrThrow("id")));
        out.put("clientRequestId", c.getString(c.getColumnIndexOrThrow("client_request_id")));
        out.put("deviceId", c.getString(c.getColumnIndexOrThrow("device_id")));
        out.put("windowId", c.getString(c.getColumnIndexOrThrow("window_id")));
        putOptional(out, "displayWindowId", c.getString(c.getColumnIndexOrThrow("display_window_id")));
        putOptional(out, "replyTarget", c.getString(c.getColumnIndexOrThrow("reply_target")));
        putOptional(out, "model", c.getString(c.getColumnIndexOrThrow("model")));
        String retryPayload = text(c.getString(c.getColumnIndexOrThrow("retry_payload_json")));
        if (!retryPayload.isEmpty()) {
            try {
                out.put("retryPayload", new JSONObject(retryPayload));
            } catch (Exception ignored) {
            }
        }
        out.put("retryPayloadSize", c.getInt(c.getColumnIndexOrThrow("retry_payload_size")));
        putOptional(out, "userMessageId", c.getString(c.getColumnIndexOrThrow("user_message_id")));
        putOptional(out, "assistantMessageId", c.getString(c.getColumnIndexOrThrow("assistant_message_id")));
        putOptional(out, "benbenMessageId", c.getString(c.getColumnIndexOrThrow("benben_message_id")));
        putOptional(out, "jobId", c.getString(c.getColumnIndexOrThrow("job_id")));
        out.put("status", c.getString(c.getColumnIndexOrThrow("status")));
        putOptional(out, "error", c.getString(c.getColumnIndexOrThrow("error")));
        out.put("createdAt", c.getString(c.getColumnIndexOrThrow("created_at")));
        out.put("updatedAt", c.getString(c.getColumnIndexOrThrow("updated_at")));
        putOptional(out, "lastAttemptAt", c.getString(c.getColumnIndexOrThrow("last_attempt_at")));
        out.put("retryCount", c.getInt(c.getColumnIndexOrThrow("retry_count")));
        out.put("schemaVersion", c.getInt(c.getColumnIndexOrThrow("schema_version")));
        return out;
    }

    private ContentValues valuesFromMessage(String deviceId, String windowId, JSONObject msg, String now) {
        String did = safe(deviceId);
        String wid = safe(windowId);
        String id = safe(msg.optString("id"));
        JSONObject tokenCount = msg.optJSONObject("tokenCount");
        ContentValues values = new ContentValues();
        values.put("message_key", messageKey(did, wid, id));
        values.put("id", id);
        values.put("device_id", did);
        values.put("window_id", wid);
        values.put("display_window_id", safe(msg.optString("displayWindowId", msg.optString("display_window_id", wid))));
        values.put("role", safe(msg.optString("role")).toLowerCase());
        values.put("content", text(msg.optString("content")));
        values.put("created_at", safe(msg.optString("createdAt", msg.optString("created_at", now))));
        values.put("updated_at", safe(msg.optString("updatedAt", msg.optString("updated_at", now))));
        values.put("status", safe(msg.optString("status", "sent")));
        values.put("client_request_id", safe(msg.optString("clientRequestId", msg.optString("client_request_id", ""))));
        values.put("operation_id", safe(msg.optString("operationId", msg.optString("operation_id", ""))));
        values.put("job_id", safe(msg.optString("jobId", msg.optString("job_id", ""))));
        values.put("reasoning", text(msg.optString("reasoning", "")));
        values.put("token_count_json", tokenCount == null ? "" : tokenCount.toString());
        values.put("remote_key", safe(msg.optString("remoteKey", msg.optString("remote_key", ""))));
        values.put("local_revision", msg.optInt("localRevision", msg.optInt("local_revision", 0)));
        values.put("deleted_at", safe(msg.optString("deletedAt", msg.optString("deleted_at", ""))));
        return values;
    }

    private ContentValues valuesFromOperation(String deviceId, String windowId, JSONObject operation, String now) {
        String did = safe(deviceId);
        String wid = safe(windowId);
        String retryPayload = "";
        JSONObject retryPayloadObject = operation.optJSONObject("retryPayload");
        if (retryPayloadObject == null) retryPayloadObject = operation.optJSONObject("retry_payload");
        if (retryPayloadObject != null) retryPayload = retryPayloadObject.toString();
        else retryPayload = text(operation.optString("retryPayload", operation.optString("retry_payload_json", "")));

        ContentValues values = new ContentValues();
        values.put("id", safe(operation.optString("id")));
        values.put("client_request_id", safe(operation.optString("clientRequestId", operation.optString("client_request_id", ""))));
        values.put("device_id", did);
        values.put("window_id", wid);
        values.put("display_window_id", safe(operation.optString("displayWindowId", operation.optString("display_window_id", wid))));
        values.put("reply_target", safe(operation.optString("replyTarget", operation.optString("reply_target", did))));
        values.put("model", safe(operation.optString("model", "")));
        values.put("retry_payload_json", retryPayload);
        values.put("retry_payload_size", operation.optInt("retryPayloadSize", operation.optInt("retry_payload_size", retryPayload.length())));
        values.put("user_message_id", safe(operation.optString("userMessageId", operation.optString("user_message_id", ""))));
        values.put("assistant_message_id", safe(operation.optString("assistantMessageId", operation.optString("assistant_message_id", ""))));
        values.put("benben_message_id", safe(operation.optString("benbenMessageId", operation.optString("benben_message_id", ""))));
        values.put("job_id", safe(operation.optString("jobId", operation.optString("job_id", ""))));
        values.put("status", safe(operation.optString("status", "draft")));
        values.put("error", safe(operation.optString("error", "")));
        values.put("created_at", safe(operation.optString("createdAt", operation.optString("created_at", now))));
        values.put("updated_at", safe(operation.optString("updatedAt", operation.optString("updated_at", now))));
        values.put("last_attempt_at", safe(operation.optString("lastAttemptAt", operation.optString("last_attempt_at", ""))));
        values.put("retry_count", operation.optInt("retryCount", operation.optInt("retry_count", 0)));
        values.put("schema_version", operation.optInt("schemaVersion", operation.optInt("schema_version", 1)));
        return values;
    }

    private static void putOptional(JSONObject out, String key, String value) throws Exception {
        String safeValue = safe(value);
        if (!safeValue.isEmpty()) out.put(key, safeValue);
    }

    private static String messageKey(String deviceId, String windowId, String messageId) {
        return safe(deviceId) + "::" + safe(windowId) + "::" + safe(messageId);
    }

    private static String safe(String value) {
        return value == null ? "" : value.trim();
    }

    private static String text(String value) {
        return value == null ? "" : value;
    }

    private static String nowIso() {
        return new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", java.util.Locale.US).format(new java.util.Date());
    }
}
