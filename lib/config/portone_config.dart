class PortOneConfig {
  const PortOneConfig._();

  static const storeId = String.fromEnvironment(
    'PORTONE_STORE_ID',
    defaultValue: 'store-ec95a751-307e-4b85-97bd-7c6fa0bbe0e2',
  );

  static const kgInicisIdentityChannelKey = String.fromEnvironment(
    'PORTONE_KG_INICIS_IDENTITY_CHANNEL_KEY',
    // PortOne Channel Key is a public client identifier embedded in the app
    // binary, not the server API Secret. Keep the production channel as the
    // portable default; local/staging builds can override it via dart-define.
    defaultValue: 'channel-key-decfd8bd-d150-4023-b4bb-982f5579bb52',
  );

  static const verificationProvider = String.fromEnvironment(
    'ADULT_VERIFICATION_PROVIDER',
    defaultValue: 'kg_inicis_via_portone',
  );

  static const pendingSessionMinutes = int.fromEnvironment(
    'ADULT_VERIFICATION_PENDING_MINUTES',
    defaultValue: 20,
  );

  static const appScheme = String.fromEnvironment(
    'PORTONE_APP_SCHEME',
    defaultValue: 'seolleyeon',
  );

  static const showDevAdultVerificationControls = bool.fromEnvironment(
    'SHOW_DEV_ADULT_VERIFICATION_CONTROLS',
    defaultValue: false,
  );
}
