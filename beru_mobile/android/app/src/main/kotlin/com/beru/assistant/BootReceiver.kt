package com.beru.assistant

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat

class BootReceiver : BroadcastReceiver() {
    companion object {
        private const val TAG = "BeruBootReceiver"
        private const val RESUME_CHANNEL_ID = "beru_boot_resume_channel"
        private const val RESUME_NOTIFICATION_ID = 1002
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.i(TAG, "Received broadcast intent action: $action")

        if (action == Intent.ACTION_BOOT_COMPLETED ||
            action == Intent.ACTION_MY_PACKAGE_REPLACED ||
            action == "android.intent.action.QUICKBOOT_POWERON"
        ) {
            // Android 14/15 blocks starting microphone foreground services from boot receivers.
            // Post an interactive notification allowing the user to tap and bring Beru into foreground.
            showResumeNotification(context)
        }
    }

    private fun showResumeNotification(context: Context) {
        val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                RESUME_CHANNEL_ID,
                "Beru Resume Alerts",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Prompts to resume Beru after device restart"
            }
            manager.createNotificationChannel(channel)
        }

        val launchIntent = Intent(context, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(context, RESUME_CHANNEL_ID)
            .setContentTitle("Beru Assistant")
            .setContentText("Tap to resume Beru listening")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()

        manager.notify(RESUME_NOTIFICATION_ID, notification)
        Log.i(TAG, "Posted 'Tap to resume Beru listening' notification after boot.")
    }
}
