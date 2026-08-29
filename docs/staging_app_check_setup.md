# Staging App Check Setup

This project uses Firebase App Check on Android/iOS/web. Debug builds use the
Firebase App Check debug provider; release builds use platform providers unless
`FORCE_APP_CHECK_DEBUG=true` is explicitly supplied for a staging-only build.

Sensitive callables set `enforceAppCheck: true` (see `functions/src/appCheckPolicy.ts`).
Without a valid App Check token, login/bootstrap and related callables are rejected.

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
   - Register the Android app `com.seolleyeon.app`.
   - For local debug/staging devices, add the debug token printed by the app log:
     `Enter this debug secret into the allow list...`
   - Do not add the debug token to source control.

3. For iOS staging:

   - Register the iOS app `com.seolleyeon.app`.
   - Use the debug provider only for debug builds.
   - Use App Attest/DeviceCheck for production-style release builds.

4. For Flutter web:

   - Register the web app in App Check and create a reCAPTCHA v3 site key.
   - Build/run with:

     ```powershell
     flutter run -d chrome --dart-define=APP_CHECK_WEB_RECAPTCHA_SITE_KEY=YOUR_SITE_KEY
     ```

   - If the key is unset, web skips App Check activation and callables that
     enforce App Check will fail (expected after SEC-P1-05).

5. Callable enforcement:

   - Auth/bootstrap and avatar/chat/team callables set `enforceAppCheck: true`.
   - Staging debug devices must have valid App Check debug tokens allowlisted
     before testing login, invites, avatar upload/polling, or contact sync.
   - Do not disable production enforcement as a staging workaround.

## Expected diagnostics

Healthy debug/staging app logs should include:

```text
[AppCheck] debugProviders=true kReleaseMode=false
```

Healthy web logs (with site key):

```text
[AppCheck] web reCAPTCHA v3 provider activated
```

If logs show `Firebase App Check API has not been used... or it is disabled`,
run the API enable command above and complete the Firebase Console registration.

If Functions logs show `Failed to validate AppCheck token` / missing token after
deploy, fix client registration (debug token or web reCAPTCHA site key) rather
than removing `enforceAppCheck`.
