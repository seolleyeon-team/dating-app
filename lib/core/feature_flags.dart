/// Compile-time feature flags for fail-closed product surfaces.
///
/// Season meeting deposits stay disabled until a real payment provider is
/// wired (`SEASON_DEPOSIT_PROVIDER_READY=true` on Functions). Clients must not
/// show payment CTAs while this flag is false.
const bool kSeasonDepositEnabled = bool.fromEnvironment(
  'SEASON_DEPOSIT_ENABLED',
  defaultValue: false,
);
