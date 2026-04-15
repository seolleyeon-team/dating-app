package com.yonsei.dating

import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.util.Base64
import android.util.Log
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayInputStream
import java.security.MessageDigest
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate

class MainActivity : FlutterActivity() {

    private val CHANNEL = "com.yonsei.dating/open_mail_app"
    private val KAKAO_CHANNEL = "com.yonsei.dating/kakao_util"
    private val SCREEN_SECURITY_CHANNEL = "com.yonsei.dating/screen_security"

    override fun onCreate(savedInstanceState: Bundle?) {
        normalizeIntentData(intent)
        super.onCreate(savedInstanceState)
        enableScreenSecurity()
        try {
            Log.d("MainActivity", "onCreate data=" + intent?.dataString)
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
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, KAKAO_CHANNEL).setMethodCallHandler { call, result ->
            if (call.method == "getKeyHash") {
                result.success(getKeyHash())
            } else if (call.method == "isDebugSigned") {
                result.success(isDebugSigned())
            } else {
                result.notImplemented()
            }
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, SCREEN_SECURITY_CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "enableProtection", "enableSensitiveProtection", "disableSensitiveProtection" -> {
                    enableScreenSecurity()
                    result.success(null)
                }
                else -> {
                    result.notImplemented()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        normalizeIntentData(intent)
        super.onNewIntent(intent)
        // app_links가 새 인텐트의 data를 읽을 수 있게 업데이트
        setIntent(intent)
        try {
            Log.d("MainActivity", "onNewIntent data=" + intent.dataString)
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
        val normalizedUri = Uri.Builder()
            .scheme("seolleyeon")
            .authority("invite")
            .path("/friend")
            .appendQueryParameter("target", target)
            .appendQueryParameter("token", token)
            .build()

        intent.data = normalizedUri
        try {
            Log.d("MainActivity", "normalized data=" + normalizedUri.toString())
        } catch (_: Exception) {
        }
    }

    private fun getKeyHash(): String {
        return try {
            val signatures = getSigningCertificates()
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

    private fun isDebugSigned(): Boolean {
        return try {
            val certificateFactory = CertificateFactory.getInstance("X.509")
            getSigningCertificates().any { signature ->
                val certificate = certificateFactory.generateCertificate(
                    ByteArrayInputStream(signature.toByteArray())
                ) as X509Certificate
                certificate.subjectX500Principal.name.contains("CN=Android Debug")
            }
        } catch (e: Exception) {
            Log.e("MainActivity", "isDebugSigned error", e)
            false
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

    private fun enableScreenSecurity() {
        window.setFlags(
            WindowManager.LayoutParams.FLAG_SECURE,
            WindowManager.LayoutParams.FLAG_SECURE
        )
    }
}
