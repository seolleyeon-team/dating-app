param(
  [int]$Seconds = 60,
  [string]$Project = "seolleyeon-final",
  [string]$Package = "com.yonsei.dating",
  [string]$FunctionService = "createfirebasecustomtoken"
)

$ErrorActionPreference = "Stop"

function Find-Adb {
  $candidates = @(@(
    (Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"),
    $(if ($env:ANDROID_HOME) { Join-Path $env:ANDROID_HOME "platform-tools\adb.exe" }),
    $(if ($env:ANDROID_SDK_ROOT) { Join-Path $env:ANDROID_SDK_ROOT "platform-tools\adb.exe" })
  ) | Where-Object { $_ -and (Test-Path $_) })

  if ($candidates.Count -gt 0) {
    return $candidates[0]
  }

  $adbCommand = Get-Command adb -ErrorAction SilentlyContinue
  if ($adbCommand) {
    return $adbCommand.Source
  }

  throw "adb was not found. Install Android SDK platform-tools or set ANDROID_HOME."
}

$adb = Find-Adb
$startLocal = Get-Date
$logcatStart = $startLocal.ToString("MM-dd HH:mm:ss.fff")
$freshnessMinutes = [Math]::Max(5, [Math]::Ceiling($Seconds / 60.0) + 2)
$freshness = "${freshnessMinutes}m"

Write-Host "Watching Kakao/Firebase diagnostics for $Seconds seconds..."
Write-Host "Project: $Project"
Write-Host "Package: $Package"
Write-Host "Started: $($startLocal.ToString("o"))"
Write-Host ""
Write-Host "Now unlock the device and tap the Kakao login button."
Write-Host "This script filters diagnostic phases only; it does not print tokens."
Write-Host ""

Start-Sleep -Seconds $Seconds

Write-Host "== Device state =="
& $adb shell pidof $Package
& $adb shell dumpsys power |
  Select-String -Pattern "mWakefulness|Display Power"
& $adb shell dumpsys window policy |
  Select-String -Pattern "isStatusBarKeyguard|mDreamingLockscreen|mScreenOn"

Write-Host ""
Write-Host "== App auth diagnostics since $logcatStart =="
$appPattern = "\[AuthDiag\]|\[FirebaseDiag\]|\[Kakao\]|firebase_custom_token|ensureFirebaseSessionForKakao|Firebase custom auth attached|permission-denied|signBlob|FirebaseAuth error|functions error|kakao_login"
& $adb logcat -d -T $logcatStart |
  Select-String -Pattern $appPattern |
  Select-Object -Last 200

Write-Host ""
Write-Host "== createFirebaseCustomToken logs ($freshness) =="
$filter = "resource.type=`"cloud_run_revision`" AND resource.labels.service_name=`"$FunctionService`""
gcloud logging read $filter `
  --project=$Project `
  --freshness=$freshness `
  --limit=50 `
  --format="table(timestamp,severity,textPayload,jsonPayload.message,jsonPayload.hasAccessToken)"
