import 'dart:async';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_ble_peripheral/flutter_ble_peripheral.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:geolocator/geolocator.dart';

import '../models/safety_stamp_verification.dart';

class SafetyStampVerificationService {
  SafetyStampVerificationService({FlutterBlePeripheral? peripheral})
    : _peripheral = peripheral ?? FlutterBlePeripheral();

  final FlutterBlePeripheral _peripheral;

  // Kept for devices that still run the previous fixed-UUID protocol.
  static const String _legacyServiceUuid =
      '9c836097-1f17-4ef8-9f0c-6b8d3f2f61a2';
  static const Duration _scanTimeout = Duration(seconds: 8);
  static const Duration _advertisingReadyTimeout = Duration(seconds: 3);
  static const Duration _peripheralReadyTimeout = Duration(seconds: 5);
  static const int _nearbyRssiThreshold = -78;
  // flutter_ble_peripheral forwards this value to
  // CBAdvertisementDataLocalNameKey on iOS, where the plugin supports up to
  // 10 bytes. Keep the optional legacy name inside that limit for iOS; the
  // primary cross-platform identifier is the per-user service UUID below.
  static const int _advertisedNameLength = 10;
  // Accept the old Android identifier while users are upgrading the app.
  static const int _legacyAdvertisedNameLength = 26;

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

    StreamSubscription<List<ScanResult>>? scanSubscription;

    try {
      final isAdvertising = await _startAdvertising(
        serviceUuid: localServiceUuid,
        localAlias: localAlias,
      );
      if (!isAdvertising) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.bluetoothOff,
          message: '블루투스 광고를 시작하지 못했어요. 블루투스를 켠 뒤 다시 시도해주세요.',
        );
      }

      final resultCompleter = Completer<int?>();
      final partnerServiceGuid = Guid(partnerServiceUuid);
      scanSubscription = FlutterBluePlus.onScanResults.listen((results) {
        for (final result in results) {
          final advertisement = result.advertisementData;
          final hasPartnerService = advertisement.serviceUuids.any(
            (service) => service == partnerServiceGuid,
          );

          if (!hasPartnerService) {
            // Legacy devices advertised the fixed UUID and relied on the
            // device name as the second half of the handshake.
            final advertisedName = advertisement.advName.trim();
            if (!partnerAliases.contains(advertisedName)) continue;
          }

          if (!resultCompleter.isCompleted) {
            resultCompleter.complete(result.rssi);
          }
          return;
        }
      });
      FlutterBluePlus.cancelWhenScanComplete(scanSubscription);

      await FlutterBluePlus.startScan(
        // The new per-user UUID is the primary identity and works on both
        // platforms. The fixed UUID remains in the filter for old builds.
        // Do not use withNames: iOS may omit or normalize local names.
        withServices: [partnerServiceGuid, Guid(_legacyServiceUuid)],
        timeout: _scanTimeout,
        androidUsesFineLocation: true,
      );

      final rssi = await resultCompleter.future.timeout(
        _scanTimeout,
        onTimeout: () => null,
      );

      if (rssi == null || rssi < _nearbyRssiThreshold) {
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
      if (FlutterBluePlus.isScanningNow) {
        await FlutterBluePlus.stopScan();
      }
      await _stopAdvertising();
    }
  }

  Future<SafetyStampVerificationResult?> _ensureBluetoothReady() async {
    if (!await FlutterBluePlus.isSupported) {
      return SafetyStampVerificationResult.failure(
        failure: SafetyStampVerificationFailure.bluetoothUnsupported,
        message: '이 기기에서는 블루투스를 사용할 수 없어 안전도장을 진행할 수 없어요.',
      );
    }

    final permission = await _peripheral.hasPermission();
    if (!_isGrantedPermissionState(permission)) {
      final requested = await _peripheral.requestPermission();
      if (!_isGrantedPermissionState(requested)) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.bluetoothPermissionDenied,
          message: '블루투스 권한이 필요해요. 권한을 허용한 뒤 다시 시도해주세요.',
        );
      }
    }

    final adapterState = await FlutterBluePlus.adapterState
        .where((state) => state != BluetoothAdapterState.unknown)
        .first;
    if (adapterState != BluetoothAdapterState.on &&
        defaultTargetPlatform == TargetPlatform.android) {
      final enabled = await _peripheral.enableBluetooth();
      if (enabled) {
        await FlutterBluePlus.adapterState
            .where((state) => state == BluetoothAdapterState.on)
            .first
            .timeout(
              const Duration(seconds: 5),
              onTimeout: () {
                return BluetoothAdapterState.off;
              },
            );
      }
    }

    if (await _waitForPeripheralBluetooth()) {
      return null;
    }

    return SafetyStampVerificationResult.failure(
      failure: SafetyStampVerificationFailure.bluetoothOff,
      message: '블루투스를 켜야 안전도장을 찍을 수 있어요. 블루투스를 켠 뒤 다시 시도해주세요.',
    );
  }

  bool _isGrantedPermissionState(BluetoothPeripheralState state) {
    return state == BluetoothPeripheralState.granted ||
        state == BluetoothPeripheralState.ready ||
        state == BluetoothPeripheralState.limited;
  }

  Future<bool> _waitForPeripheralBluetooth() async {
    final deadline = DateTime.now().add(_peripheralReadyTimeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _peripheral.isBluetoothOn) return true;
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    return false;
  }

  Future<bool> _startAdvertising({
    required String serviceUuid,
    required String localAlias,
  }) async {
    final advertiseData = AdvertiseData(
      serviceUuid: serviceUuid,
      localName: localAlias,
    );

    await _peripheral.stop();
    await _peripheral.start(advertiseData: advertiseData);
    final deadline = DateTime.now().add(_advertisingReadyTimeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _peripheral.isAdvertising) return true;
      await Future<void>.delayed(const Duration(milliseconds: 150));
    }
    return false;
  }

  Future<void> _stopAdvertising() async {
    try {
      await _peripheral.stop();
    } catch (_) {
      // 광고 중지가 실패해도 다음 시도를 막지 않도록 무시한다.
    }
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
