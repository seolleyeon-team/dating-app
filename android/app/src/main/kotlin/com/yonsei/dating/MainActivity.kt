package com.yonsei.dating

import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Base64
import android.util.Log
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.MessageDigest

class MainActivity : FlutterActivity() {

    private val CHANNEL = "com.yonsei.dating/open_mail_app"
    private val KAKAO_CHANNEL = "com.yonsei.dating/kakao_util"

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
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, KAKAO_CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "getKeyHash") {
                result.success(getKeyHash())
            } else {
                result.notImplemented()
            }
        }
    }

    private fun getKeyHash(): String {
        return try {
            @Suppress("DEPRECATION")
            val signatures = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                packageManager.getPackageInfo(
                    packageName,
                    PackageManager.GET_SIGNING_CERTIFICATES
                ).signingInfo?.apkContentsSigners
            } else {
                packageManager.getPackageInfo(
                    packageName,
                    PackageManager.GET_SIGNATURES
                ).signatures
            }) ?: emptyArray()
            if (signatures.isNotEmpty()) {
                val md = MessageDigest.getInstance("SHA")
                md.update(signatures[0].toByteArray())
                Base64.encodeToString(md.digest(), Base64.NO_WRAP).trim()
            } else {
                ""
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "getKeyHash error", e)
            ""
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
