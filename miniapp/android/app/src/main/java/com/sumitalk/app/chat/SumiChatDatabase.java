package com.sumitalk.app.chat;

import android.content.Context;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

public class SumiChatDatabase extends SQLiteOpenHelper {
    private static final String DB_NAME = "sumitalk_chat_store.db";
    private static final int DB_VERSION = 2;

    public SumiChatDatabase(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
                "CREATE TABLE IF NOT EXISTS chat_messages ("
                        + "message_key TEXT PRIMARY KEY,"
                        + "id TEXT NOT NULL,"
                        + "device_id TEXT NOT NULL,"
                        + "window_id TEXT NOT NULL,"
                        + "display_window_id TEXT,"
                        + "role TEXT NOT NULL,"
                        + "content TEXT NOT NULL,"
                        + "created_at TEXT NOT NULL,"
                        + "updated_at TEXT NOT NULL,"
                        + "status TEXT,"
                        + "client_request_id TEXT,"
                        + "operation_id TEXT,"
                        + "job_id TEXT,"
                        + "reasoning TEXT,"
                        + "token_count_json TEXT,"
                        + "attachments_json TEXT,"
                        + "remote_key TEXT,"
                        + "local_revision INTEGER DEFAULT 0,"
                        + "deleted_at TEXT"
                        + ")"
        );
        db.execSQL(
                "CREATE TABLE IF NOT EXISTS chat_operations ("
                        + "id TEXT PRIMARY KEY,"
                        + "client_request_id TEXT NOT NULL,"
                        + "device_id TEXT NOT NULL,"
                        + "window_id TEXT NOT NULL,"
                        + "display_window_id TEXT,"
                        + "reply_target TEXT,"
                        + "model TEXT,"
                        + "retry_payload_json TEXT,"
                        + "retry_payload_size INTEGER DEFAULT 0,"
                        + "user_message_id TEXT,"
                        + "assistant_message_id TEXT,"
                        + "benben_message_id TEXT,"
                        + "job_id TEXT,"
                        + "status TEXT NOT NULL,"
                        + "error TEXT,"
                        + "created_at TEXT NOT NULL,"
                        + "updated_at TEXT NOT NULL,"
                        + "last_attempt_at TEXT,"
                        + "retry_count INTEGER DEFAULT 0,"
                        + "schema_version INTEGER DEFAULT 1"
                        + ")"
        );
        db.execSQL(
                "CREATE TABLE IF NOT EXISTS chat_meta ("
                        + "key TEXT PRIMARY KEY,"
                        + "value TEXT,"
                        + "updated_at TEXT NOT NULL"
                        + ")"
        );
        createIndexes(db);
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        onCreate(db);
        if (oldVersion < 2) {
            try {
                db.execSQL("ALTER TABLE chat_messages ADD COLUMN attachments_json TEXT");
            } catch (Exception ignored) {
            }
        }
    }

    private void createIndexes(SQLiteDatabase db) {
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_chat_messages_window_created ON chat_messages(device_id, window_id, created_at)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_chat_messages_client_request ON chat_messages(client_request_id)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_chat_messages_operation ON chat_messages(operation_id)");
        db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_operations_client_window_target ON chat_operations(client_request_id, window_id, reply_target)");
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_chat_operations_window_status_updated ON chat_operations(window_id, status, updated_at)");
    }
}
