package com.dugateway.healthexecutor

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

class HealthSyncWorker(
    appContext: Context,
    workerParams: WorkerParameters
) : CoroutineWorker(appContext, workerParams) {

    companion object {
        // TODO: 改成你的网关域名
        private const val GATEWAY_URL = "https://duxy-home.com/api/sense"
    }

    override suspend fun doWork(): Result {
        if (HealthConnectClient.getSdkStatus(applicationContext) != HealthConnectClient.SDK_AVAILABLE) {
            return Result.retry()
        }

        val client = HealthConnectClient.getOrCreate(applicationContext)
        val now = Instant.now()
        val heartRate = readLatestHeartRate(client, now)
        val steps = readTodaySteps(client, now)

        // 心率和步数都没有就不发
        if (heartRate == null && steps == null) {
            return Result.success()
        }

        val payload = buildString {
            append("{\"type\":\"health\"")
            if (heartRate != null) append(",\"heart_rate\":").append(heartRate)
            if (steps != null) append(",\"steps\":").append(steps)
            append(",\"timestamp\":").append(now.epochSecond)
            append("}")
        }

        val body = payload.toRequestBody("application/json".toMediaType())
        val req = Request.Builder()
            .url(GATEWAY_URL)
            .post(body)
            .build()

        return try {
            OkHttpClient().newCall(req).execute().use { resp ->
                if (resp.isSuccessful) Result.success() else Result.retry()
            }
        } catch (_: Exception) {
            Result.retry()
        }
    }

    private suspend fun readLatestHeartRate(client: HealthConnectClient, now: Instant): Int? {
        return try {
            val range = TimeRangeFilter.between(now.minusSeconds(4 * 3600), now)
            val resp = client.readRecords(
                ReadRecordsRequest(
                    recordType = HeartRateRecord::class,
                    timeRangeFilter = range,
                    ascendingOrder = false,
                    pageSize = 1
                )
            )
            val sample = resp.records.firstOrNull()?.samples?.maxByOrNull { it.time }
            sample?.beatsPerMinute?.toInt()
        } catch (_: Exception) {
            null
        }
    }

    private suspend fun readTodaySteps(client: HealthConnectClient, now: Instant): Long? {
        return try {
            val zone = ZoneId.systemDefault()
            val startOfDay = LocalDate.now(zone).atStartOfDay(zone).toInstant()
            val aggregate = client.aggregate(
                AggregateRequest(
                    metrics = setOf(StepsRecord.COUNT_TOTAL),
                    timeRangeFilter = TimeRangeFilter.between(startOfDay, now)
                )
            )
            aggregate[StepsRecord.COUNT_TOTAL]
        } catch (_: Exception) {
            null
        }
    }
}
