package com.seolleyeon.app

import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.security.MessageDigest
import java.util.Locale

class MainActivity : FlutterActivity() {

    companion object {
        // TEMPORARY: disabled for internal-test screenshot collection.
        // Set this back to true before the production release.
        private const val SCREEN_CAPTURE_PROTECTION_ENABLED = false
    }

    private val CHANNEL = "com.seolleyeon.app/open_mail_app"
    private val SCREEN_SECURITY_CHANNEL = "com.seolleyeon.app/screen_security"
    private val RUNTIME_DIAGNOSTIC_CHANNEL = "com.seolleyeon.app/runtime_diagnostics"

    override fun onCreate(savedInstanceState: Bundle?) {
        normalizeIntentData(intent)
        super.onCreate(savedInstanceState)
        applyScreenSecurityPolicy()
        try {
            // Never log intent data: a share link carries a bearer invite token.
            Log.d("MainActivity", "onCreate hasLinkData=" + (intent?.data != null))
        } catch (_: Exception) {
        }
    }

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
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SCREEN_SECURITY_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "enableProtection", "enableSensitiveProtection", "disableSensitiveProtection" -> {
                    applyScreenSecurityPolicy()
                    result.success(null)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, RUNTIME_DIAGNOSTIC_CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "getAppCheck") {
                result.success(appCheckRuntimeDiagnostics())
            } else {
                result.notImplemented()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        normalizeIntentData(intent)
        super.onNewIntent(intent)
        // app_links가 새 인텐트의 data를 읽을 수 있게 업데이트
        setIntent(intent)
        try {
            Log.d("MainActivity", "onNewIntent hasLinkData=" + (intent.data != null))
        } catch (_: Exception) {
        }
    }

    private fun normalizeIntentData(intent: Intent?) {
        if (intent == null) return

        val hasTokenInData = intent.dataString?.contains("token=") == true
        if (hasTokenInData) return

        val token = intent.getStringExtra("token")
        if (token.isNullOrBlank()) return

        val target = intent.getStringExtra("target") ?: "friend_invite"
        // The Dart parser fails closed when the path and the target
        // disagree, so the path must follow the target.
        val path = if (target == "team_invite") "/team" else "/friend"
        val normalizedUri = Uri.Builder()
            .scheme("seolleyeon")
            .authority("invite")
            .path(path)
            .appendQueryParameter("target", target)
            .appendQueryParameter("token", token)
            .build()

        intent.data = normalizedUri
        try {
            Log.d("MainActivity", "normalized intent extras into invite scheme target=" + target)
        } catch (_: Exception) {
        }
    }

    private fun getSigningCertificates() =
        @Suppress("DEPRECATION")
        (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
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

    private fun appCheckRuntimeDiagnostics(): Map<String, Any> {
        val packageInfo = packageManager.getPackageInfo(packageName, 0)
        val installerPackage = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                packageManager.getInstallSourceInfo(packageName).installingPackageName
            } else {
                @Suppress("DEPRECATION")
                packageManager.getInstallerPackageName(packageName)
            }
        } catch (_: Exception) {
            null
        }
        return mapOf(
            "packageName" to packageName,
            "versionName" to (packageInfo.versionName ?: "확인 불가"),
            "versionCode" to if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                packageInfo.longVersionCode.toString()
            } else {
                @Suppress("DEPRECATION")
                packageInfo.versionCode.toString()
            },
            "installerPackage" to (installerPackage ?: "확인 불가"),
            "signingCertificateSha256" to getSigningCertificates().map { signature ->
                MessageDigest.getInstance("SHA-256")
                    .digest(signature.toByteArray())
                    .joinToString(":") { byte -> "%02X".format(Locale.US, byte.toInt() and 0xff) }
            },
        )
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

    private fun applyScreenSecurityPolicy() {
        if (SCREEN_CAPTURE_PROTECTION_ENABLED) {
            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        } else {
            window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
        }
    }
}
