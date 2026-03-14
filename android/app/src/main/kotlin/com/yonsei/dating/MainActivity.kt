package com.yonsei.dating

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {

    private val CHANNEL = "com.yonsei.dating/open_mail_app"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "launchGmail") {
                val launched = launchAppByPackage("com.google.android.gm")
                result.success(launched)
            } else {
                result.notImplemented()
            }
        }
    }

    private fun launchAppByPackage(packageName: String): Boolean {
        return try {
            var launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            if (launchIntent == null) {
                // getLaunchIntentForPackage가 null일 때 수동으로 MAIN+LAUNCHER 인텐트 생성
                launchIntent = Intent(Intent.ACTION_MAIN).apply {
                    setPackage(packageName)
                    addCategory(Intent.CATEGORY_LAUNCHER)
                }
                if (packageManager.resolveActivity(launchIntent, 0) == null) {
                    return false
                }
            }
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(launchIntent)
            true
        } catch (e: Exception) {
            false
        }
    }
}
