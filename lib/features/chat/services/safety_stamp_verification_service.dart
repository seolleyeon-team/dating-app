import 'dart:async';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_ble_peripheral/flutter_ble_peripheral.dart';
import 'package:geolocator/geolocator.dart';

import '../models/safety_stamp_verification.dart';
import 'safety_stamp_ble_transport.dart';

/// Keeps this device discoverable for the safety-stamp proximity check.
///
/// AUD-06: a device used to advertise only while its OWN stamp attempt ran
/// (about eight seconds) and stopped in that attempt's `finally`. Each side
/// scans for the other side's advertisement, so once A had stamped (or had
/// simply failed once) A was silent, and B could never find A: the phase
/// could only complete when both taps overlapped by chance, and a retry
/// after a one-sided success could never succeed.
///
/// The advertisement is now a "presence" with its own lifetime, independent
/// of the local attempt: it starts when the stamp screen opens or an attempt
/// begins, survives the attempt (success or failure), and ends when the
/// phase is reported complete for both sides or [holdDuration] passes
/// without activity. That bound is the battery / privacy limit.
///
/// There is one radio, so this is process-wide state: a new screen (and its
/// new service instance) takes over the same presence instead of fighting a
/// stale one.
class SafetyStampPresence with WidgetsBindingObserver {
  SafetyStampPresence._();

  /// A second, independent presence. Tests use one per simulated device.
  @visibleForTesting
  SafetyStampPresence.detached();

  static final SafetyStampPresence instance = SafetyStampPresence._();

  /// How long the device stays discoverable after the last activity (screen
  /// opened, attempt started or finished).
  static const Duration holdDuration = Duration(minutes: 10);

  SafetyStampBleTransport? _transport;
  String? _serviceUuid;
  String? _localName;
  Timer? _expiry;
  bool _observing = false;

  /// The advertised service UUID while a presence is held, else null.
  @visibleForTesting
  String? get heldServiceUuid => _serviceUuid;

  bool get isHeld => _serviceUuid != null;

  /// Starts (or keeps) advertising [serviceUuid] and (re)starts the hold
  /// timer. Returns whether the platform reports the advertisement running.
  Future<bool> hold({
    required SafetyStampBleTransport transport,
    required String serviceUuid,
    required String localName,
    Duration duration = holdDuration,
  }) async {
    final sameIdentity = _serviceUuid == serviceUuid;
    _transport = transport;
    _serviceUuid = serviceUuid;
    _localName = localName;
    _restartExpiry(duration);
    _startObserving();

    try {
      if (sameIdentity && await transport.isAdvertising()) return true;
      final advertising = await transport.startAdvertising(
        serviceUuid: serviceUuid,
        localName: localName,
      );
      if (!advertising && _serviceUuid == serviceUuid) {
        // Nothing is on air: do not pretend a presence exists.
        await release();
      }
      return advertising;
    } catch (_) {
      if (_serviceUuid == serviceUuid) await release();
      rethrow;
    }
  }

  /// Extends the hold without touching the radio (an attempt just finished).
  void extend({Duration duration = holdDuration}) {
    if (!isHeld) return;
    _restartExpiry(duration);
  }

  /// Stops advertising now: the phase is complete for both sides, or the
  /// hold expired.
  Future<void> release() async {
    final transport = _transport;
    _expiry?.cancel();
    _expiry = null;
    _transport = null;
    _serviceUuid = null;
    _localName = null;
    _stopObserving();
    if (transport == null) return;
    try {
      await transport.stopAdvertising();
    } catch (_) {
      // 광고 중지가 실패해도 다음 시도를 막지 않도록 무시한다.
    }
  }

  void _restartExpiry(Duration duration) {
    _expiry?.cancel();
    _expiry = Timer(duration, () {
      _expiry = null;
      unawaited(release());
    });
  }

  void _startObserving() {
    if (_observing) return;
    _observing = true;
    WidgetsBinding.instance.addObserver(this);
  }

  void _stopObserving() {
    if (!_observing) return;
    _observing = false;
    WidgetsBinding.instance.removeObserver(this);
  }

  /// The OS may stop an advertisement while the app is in the background
  /// (iOS suspends it, Android may reclaim it). The presence is not dropped
  /// on backgrounding - the partner may be stamping right now - and it is
  /// put back on air when the app returns, if the hold is still running.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(reassert());
    }
  }

  @visibleForTesting
  Future<void> reassert() async {
    final transport = _transport;
    final serviceUuid = _serviceUuid;
    final localName = _localName;
    if (transport == null || serviceUuid == null || localName == null) return;
    try {
      if (await transport.isAdvertising()) return;
      if (!await transport.hasPermission()) return;
      if (!await transport.isBluetoothOn()) return;
      if (_serviceUuid != serviceUuid) return;
      await transport.startAdvertising(
        serviceUuid: serviceUuid,
        localName: localName,
      );
    } catch (_) {
      // Best effort: the next attempt starts advertising again anyway.
    }
  }

  @visibleForTesting
  Future<void> resetForTest() => release();
}

class SafetyStampVerificationService {
  SafetyStampVerificationService({
    FlutterBlePeripheral? peripheral,
    SafetyStampBleTransport? transport,
    @visibleForTesting
    Future<SafetyStampVerificationResult> Function()? captureLocation,
    @visibleForTesting Duration scanTimeout = _defaultScanTimeout,
    @visibleForTesting SafetyStampPresence? presence,
  }) : _presence = presence ?? SafetyStampPresence.instance,
       _transport =
           transport ?? FlutterSafetyStampBleTransport(peripheral: peripheral),
       _captureLocationOverride = captureLocation,
       _scanTimeout = scanTimeout;

  final SafetyStampBleTransport _transport;
  final Future<SafetyStampVerificationResult> Function()?
  _captureLocationOverride;
  final Duration _scanTimeout;
  final SafetyStampPresence _presence;

  // Kept for devices that still run the previous fixed-UUID protocol.
  static const String _legacyServiceUuid =
      '9c836097-1f17-4ef8-9f0c-6b8d3f2f61a2';
  static const Duration _defaultScanTimeout = Duration(seconds: 8);
  static const int _nearbyRssiThreshold = -78;
  // flutter_ble_peripheral forwards this value to
  // CBAdvertisementDataLocalNameKey on iOS, where the plugin supports up to
  // 10 bytes. Keep the optional legacy name inside that limit for iOS; the
  // primary cross-platform identifier is the per-user service UUID below.
  static const int _advertisedNameLength = 10;
  // Accept the old Android identifier while users are upgrading the app.
  static const int _legacyAdvertisedNameLength = 26;

  /// Makes this device discoverable for [promiseId] WITHOUT asking for
  /// anything: it only starts when Bluetooth is supported, already permitted
  /// and already on. Call it when the stamp screen opens, so the partner's
  /// attempt can succeed before the local user has tapped. A later
  /// [verifyNearbyAndCaptureLocation] does the prompting.
  ///
  /// Returns whether the device is advertising.
  Future<bool> startPresence({
    required String promiseId,
    required String currentUserId,
  }) async {
    if (kIsWeb || promiseId.isEmpty || currentUserId.isEmpty) return false;
    try {
      if (!await _transport.isSupported()) return false;
      if (!await _transport.hasPermission()) return false;
      if (!await _transport.isBluetoothOn()) return false;
      return await _presence.hold(
        transport: _transport,
        serviceUuid: _buildAdvertisedServiceUuid(
          promiseId: promiseId,
          userId: currentUserId,
        ),
        localName: _buildAdvertisedAlias(
          promiseId: promiseId,
          userId: currentUserId,
        ),
      );
    } catch (_) {
      return false;
    }
  }

  /// The stamp phase is complete for BOTH sides (or the promise is gone):
  /// nobody needs to find this device any more, stop advertising now.
  Future<void> completePresence() => _presence.release();

  Future<SafetyStampVerificationResult> verifyNearbyAndCaptureLocation({
    required String promiseId,
    required String currentUserId,
    required String partnerUserId,
    bool preferGpsOnly = false,
  }) async {
    if (kIsWeb || preferGpsOnly) {
      final location = await _captureLocation();
      if (!location.isSuccess) {
        return location;
      }

      return SafetyStampVerificationResult.success(
        message: preferGpsOnly
            ? '상대가 웹에서 접속 중이라 현재 위치를 기준으로 안전도장을 기록했어요.'
            : '웹에서는 현재 위치를 기준으로 안전도장을 기록했어요.',
        rssi: 0,
        location: location.location!,
      );
    }

    final bluetoothReady = await _ensureBluetoothReady();
    if (bluetoothReady != null) {
      return bluetoothReady;
    }

    final localServiceUuid = _buildAdvertisedServiceUuid(
      promiseId: promiseId,
      userId: currentUserId,
    );
    final partnerServiceUuid = _buildAdvertisedServiceUuid(
      promiseId: promiseId,
      userId: partnerUserId,
    );
    final localAlias = _buildAdvertisedAlias(
      promiseId: promiseId,
      userId: currentUserId,
    );
    final partnerAliases = <String>{
      _buildAdvertisedAlias(promiseId: promiseId, userId: partnerUserId),
      // A recently built iOS app can still be paired with an older Android
      // build that is broadcasting the previous 26-byte identifier.
      _buildAdvertisedAlias(
        promiseId: promiseId,
        userId: partnerUserId,
        maxLength: _legacyAdvertisedNameLength,
      ),
    };

    StreamSubscription<int>? scanSubscription;

    try {
      final isAdvertising = await _presence.hold(
        transport: _transport,
        serviceUuid: localServiceUuid,
        localName: localAlias,
      );
      if (!isAdvertising) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.bluetoothOff,
          message: '블루투스 광고를 시작하지 못했어요. 블루투스를 켠 뒤 다시 시도해주세요.',
        );
      }

      // The first sighting can be a weak outlier. Keep listening until one
      // is close enough or the scan window ends, instead of failing the
      // whole attempt on a single sample.
      final nearby = Completer<int?>();
      scanSubscription = _transport
          .scanForPartner(
            partnerServiceUuid: partnerServiceUuid,
            legacyServiceUuid: _legacyServiceUuid,
            partnerNames: partnerAliases,
            timeout: _scanTimeout,
          )
          .listen(
            (rssi) {
              if (rssi >= _nearbyRssiThreshold && !nearby.isCompleted) {
                nearby.complete(rssi);
              }
            },
            onError: (Object error) {
              if (!nearby.isCompleted) nearby.completeError(error);
            },
          );

      final rssi = await nearby.future.timeout(
        _scanTimeout,
        onTimeout: () => null,
      );

      if (rssi == null) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.partnerNotNearby,
          message: '상대방이 충분히 가까이 있어야 안전도장을 찍을 수 있어요. 휴대폰을 더 가까이 두고 다시 시도해주세요.',
        );
      }

      final location = await _captureLocation();
      if (!location.isSuccess) return location;

      return SafetyStampVerificationResult.success(
        message: '근처에서 상대방과 현재 위치가 확인되었어요.',
        rssi: rssi,
        location: location.location!,
      );
    } catch (_) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.unknown,
        message: '근처 기기 확인 중 문제가 발생했어요. 잠시 후 다시 시도해주세요.',
      );
    } finally {
      await scanSubscription?.cancel();
      try {
        await _transport.stopScan();
      } catch (_) {
        // 스캔 중지가 실패해도 다음 시도를 막지 않도록 무시한다.
      }
      // AUD-06: the advertisement is NOT stopped here. Whether this attempt
      // succeeded or not, the partner may still need to find this device;
      // the presence ends by completePresence() or by its own timeout.
      _presence.extend();
    }
  }

  Future<SafetyStampVerificationResult?> _ensureBluetoothReady() async {
    if (!await _transport.isSupported()) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.bluetoothUnsupported,
        message: '이 기기에서는 블루투스를 사용할 수 없어 안전도장을 진행할 수 없어요.',
      );
    }

    if (!await _transport.hasPermission()) {
      if (!await _transport.requestPermission()) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.bluetoothPermissionDenied,
          message: '블루투스 권한이 필요해요. 권한을 허용한 뒤 다시 시도해주세요.',
        );
      }
    }

    if (await _transport.ensureBluetoothOn()) {
      return null;
    }

    return SafetyStampVerificationResult.failure(
      failure: SafetyStampVerificationFailure.bluetoothOff,
      message: '블루투스를 켜야 안전도장을 찍을 수 있어요. 블루투스를 켠 뒤 다시 시도해주세요.',
    );
  }

  String _buildAdvertisedAlias({
    required String promiseId,
    required String userId,
    int maxLength = _advertisedNameLength,
  }) {
    final digest = sha1.convert('$promiseId::$userId'.codeUnits).toString();
    return 'SYN${digest.substring(0, maxLength - 3)}';
  }

  String _buildAdvertisedServiceUuid({
    required String promiseId,
    required String userId,
  }) {
    final digest = sha1.convert('$promiseId::$userId'.codeUnits).toString();
    final variantNibble =
        ((int.parse(digest.substring(16, 17), radix: 16) & 0x3) | 0x8)
            .toRadixString(16);

    // Turn the first 128 bits of the digest into a valid UUID. The version and
    // variant bits make the value acceptable to CoreBluetooth and Android's
    // UUID parser while retaining deterministic, promise-scoped identity.
    return '${digest.substring(0, 8)}-${digest.substring(8, 12)}-4${digest.substring(13, 16)}-$variantNibble${digest.substring(17, 20)}-${digest.substring(20, 32)}';
  }

  Future<SafetyStampVerificationResult> _captureLocation() async {
    final override = _captureLocationOverride;
    if (override != null) return override();

    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.locationServiceDisabled,
        message: '위치 서비스를 켜야 안전도장 위치를 저장할 수 있어요.',
      );
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.locationPermissionDenied,
        message: '위치 권한이 필요해요. 권한을 허용한 뒤 다시 시도해주세요.',
      );
    }

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );

      return SafetyStampVerificationResult.success(
        message: '위치까지 함께 확인했어요.',
        rssi: 0,
        location: SafetyStampLocationSnapshot(
          latitude: position.latitude,
          longitude: position.longitude,
          accuracyMeters: position.accuracy,
          capturedAt: position.timestamp.toLocal(),
        ),
      );
    } catch (_) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.locationUnavailable,
        message: '현재 위치를 가져오지 못했어요. 잠시 후 다시 시도해주세요.',
      );
    }
  }
}
