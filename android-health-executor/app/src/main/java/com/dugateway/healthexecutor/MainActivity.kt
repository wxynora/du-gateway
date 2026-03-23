package com.dugateway.healthexecutor

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.lifecycle.lifecycleScope
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {
    private val permissions = setOf(
        HealthPermission.getReadPermission(HeartRateRecord::class),
        HealthPermission.getReadPermission(StepsRecord::class)
    )

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted ->
        if (granted.containsAll(permissions)) {
            scheduleWorker()
            findViewById<TextView>(android.R.id.text1).text =
                "权限已开，执行器已启动（每15分钟上报一次）"
        } else {
            findViewById<TextView>(android.R.id.text1).text =
                "未拿到 Health Connect 权限，请手动允许心率/步数读取"
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = TextView(this)
        tv.id = android.R.id.text1
        tv.textSize = 16f
        tv.setPadding(40, 80, 40, 40)
        tv.text = "正在检查 Health Connect..."
        setContentView(tv)

        when (HealthConnectClient.getSdkStatus(this)) {
            HealthConnectClient.SDK_UNAVAILABLE -> {
                tv.text = "此设备不支持 Health Connect"
            }
            HealthConnectClient.SDK_UNAVAILABLE_PROVIDER_UPDATE_REQUIRED -> {
                tv.text = "请先安装/更新 Health Connect 后重试"
            }
            else -> {
                val client = HealthConnectClient.getOrCreate(this)
                requestIfNeeded(client)
            }
        }
    }

    private fun requestIfNeeded(client: HealthConnectClient) {
        lifecycleScope.launchWhenStarted {
            val granted = client.permissionController.getGrantedPermissions()
            if (granted.containsAll(permissions)) {
                scheduleWorker()
                findViewById<TextView>(android.R.id.text1).text =
                    "权限已开，执行器已启动（每15分钟上报一次）"
            } else {
                permissionLauncher.launch(permissions)
            }
        }
    }

    private fun scheduleWorker() {
        val req = PeriodicWorkRequestBuilder<HealthSyncWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "health_sync_worker",
            ExistingPeriodicWorkPolicy.UPDATE,
            req
        )
    }
}
