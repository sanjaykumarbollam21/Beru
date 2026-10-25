package com.beru.assistant

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat

class BeruForegroundService : Service() {

    companion object {
        const val CHANNEL_ID = "beru_listening_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_START = "com.beru.action.START"
        const val ACTION_STOP = "com.beru.action.STOP"
        const val ACTION_RESTART_LISTENING = "com.beru.action.RESTART_LISTENING"
    }

    private var isListening: Boolean = true

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action ?: ACTION_START

        when (action) {
            ACTION_STOP -> {
                isListening = false
                stopForeground(true)
                stopSelf()
            }
            ACTION_RESTART_LISTENING -> {
                isListening = true
                try {
                    startForeground(NOTIFICATION_ID, buildNotification(true))
                } catch (e: SecurityException) {
                    android.util.Log.w("BeruForegroundService", "Microphone permission not granted for FGS: ${e.message}")
                    stopSelf()
                }
            }
            else -> {
                isListening = true
                try {
                    startForeground(NOTIFICATION_ID, buildNotification(true))
                } catch (e: SecurityException) {
                    android.util.Log.w("BeruForegroundService", "Microphone permission not granted for FGS: ${e.message}")
                    stopSelf()
                }
            }
        }

        // START_STICKY ensures Android restarts the service if killed by memory pressure
        return START_STICKY
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Beru Assistant Background Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Beru connected to the hub and listening for 'Hey Beru'"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(listening: Boolean): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val title = if (listening) "Beru is listening" else "Beru is paused"
        val content = if (listening) "Connected to Hub • Ready for 'Hey Beru'" else "Tap to resume listening"

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(content)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
