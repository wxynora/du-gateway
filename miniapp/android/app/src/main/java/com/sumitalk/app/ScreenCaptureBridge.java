package com.sumitalk.app;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;

final class ScreenCaptureBridge {
    private static final ConcurrentHashMap<String, Pending> PENDING = new ConcurrentHashMap<>();

    private ScreenCaptureBridge() {
    }

    static void create(String requestId) {
        if (requestId == null || requestId.trim().isEmpty()) return;
        PENDING.put(requestId, new Pending());
    }

    static JSONObject await(String requestId, long timeoutMs) throws InterruptedException {
        Pending pending = PENDING.get(requestId);
        if (pending == null) return null;
        try {
            pending.latch.await(Math.max(1000L, timeoutMs), TimeUnit.MILLISECONDS);
            return pending.result.get();
        } finally {
            PENDING.remove(requestId);
        }
    }

    static void complete(String requestId, JSONObject result) {
        Pending pending = PENDING.get(requestId);
        if (pending == null) return;
        pending.result.compareAndSet(null, result == null ? new JSONObject() : result);
        pending.latch.countDown();
    }

    private static final class Pending {
        final CountDownLatch latch = new CountDownLatch(1);
        final AtomicReference<JSONObject> result = new AtomicReference<>();
    }
}
