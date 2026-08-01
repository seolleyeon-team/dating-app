class PortOneConfig {
  const PortOneConfig._();

  static const storeId = String.fromEnvironment(
    'PORTONE_STORE_ID',
    defaultValue: 'store-ec95a751-307e-4b85-97bd-7c6fa0bbe0e2',
  );

  static const kgInicisIdentityChannelKey = String.fromEnvironment(
    'PORTONE_KG_INICIS_IDENTITY_CHANNEL_KEY',
    defaultValue: 'channel-key-283ccf6b-ed74-4541-b74e-916c7df010eb',
  );

  static const verificationProvider = String.fromEnvironment(
    'ADULT_VERIFICATION_PROVIDER',
    defaultValue: 'kg_inicis_via_portone_test',
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
