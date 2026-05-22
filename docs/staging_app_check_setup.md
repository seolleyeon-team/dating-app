# Staging App Check Setup

This project uses Firebase App Check on Android/iOS. Debug builds use the
Firebase App Check debug provider; release builds use platform providers unless
`FORCE_APP_CHECK_DEBUG=true` is explicitly supplied for a staging-only build.

Do not commit debug tokens, Firebase tokens, service account keys, or private
logs.

## seolleyeon-final checklist

1. Enable the API:

   ```powershell
   gcloud services enable firebaseappcheck.googleapis.com --project=seolleyeon-final
   ```

2. In Firebase Console:

   - Open `seolleyeon-final`.
   - Go to Build -> App Check -> Get started.
   - Register the Android app `com.yonsei.dating`.
   - For local debug/staging devices, add the debug token printed by the app log:
     `Enter this debug secret into the allow list...`
   - Do not add the debug token to source control.

3. For iOS staging:

   - Register the iOS app `com.yonsei.dating`.
   - Use the debug provider only for debug builds.
   - Use App Attest/DeviceCheck for production-style release builds.

4. Callable enforcement:

   - Current avatar callables do not set `enforceAppCheck`.
   - If enforcement is enabled later, staging debug devices must have valid
     App Check debug tokens allowlisted before testing avatar upload/polling.
   - Do not disable production enforcement as a staging workaround.

## Expected diagnostics

Healthy debug/staging app logs should include:

```text
[AppCheck] debugProviders=true kReleaseMode=false
```

If logs show `Firebase App Check API has not been used... or it is disabled`,
run the API enable command above and complete the Firebase Console registration.

If Functions logs show `AppCheck token was rejected` but also `enforcement is
disabled`, the callable may still run, but the client can see token refresh
retries or throttling. Fix the App Check registration/debug token instead of
weakening auth or privacy rules.
