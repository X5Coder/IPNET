package com.ipnet.android

import android.content.Context
import android.content.Intent
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * Real auto-refresh: every 30 min re-read the public repo snapshot
 * (same check as the desktop loop). If bore published a new port,
 * restart ProxyVpnService with the new endpoint — no taps needed.
 * Read-only safe: never dispatches, only follows the owner's renewals.
 */
class EndpointWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val cfg = Prefs.load(applicationContext)
        val owner = cfg["owner"].orEmpty()
        val repo = cfg["repo"].orEmpty()
        if (owner.isEmpty() || repo.isEmpty()) return Result.success()
        return try {
            val snap = RepoCheck.snapshot(owner, repo)
            if (snap.endpoint.isEmpty() || snap.password.isEmpty()) return Result.success()
            val (h, p) = snap.endpoint.split(":")
            val curHost = cfg["host"].orEmpty()
            val curPort = cfg["port"].orEmpty()
            if (h != curHost || p != curPort || snap.password != cfg["password"]) {
                Prefs.save(applicationContext, owner, repo, h, p.toInt(), snap.password, snap.method)
                val i = Intent(applicationContext, ProxyVpnService::class.java).apply {
                    putExtra("ss_host", h)
                    putExtra("ss_port", p.toInt())
                    putExtra("ss_password", snap.password)
                    putExtra("ss_method", snap.method)
                }
                applicationContext.startForegroundService(i)
            }
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val NAME = "endpoint-watch"

        fun schedule(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<EndpointWorker>(30, TimeUnit.MINUTES).build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                NAME, ExistingPeriodicWorkPolicy.KEEP, req,
            )
        }

        fun cancel(ctx: Context) = WorkManager.getInstance(ctx).cancelUniqueWork(NAME)
    }
}
