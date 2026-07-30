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

  // Temporary override: allow safety stamps even when nearby verification fails.
  static const bool _disableNearbyRequirement = true;
  // Temporary override: allow safety stamps even when location capture fails.
  static const bool _disableLocationRequirement = true;
  static const String _serviceUuid = '9c836097-1f17-4ef8-9f0c-6b8d3f2f61a2';
  static const Duration _scanTimeout = Duration(seconds: 8);
  static const int _nearbyRssiThreshold = -78;
  static const int _maxAdvertisedNameLength = 26;

  Future<SafetyStampVerificationResult> verifyNearbyAndCaptureLocation({
    required String promiseId,
    required String currentUserId,
    required String partnerUserId,
    bool preferGpsOnly = false,
  }) async {
    if (_disableLocationRequirement) {
      return SafetyStampVerificationResult.success(
        message: _disableNearbyRequirement
            ? '상대 거리와 현재 위치 확인 없이 안전도장을 준비했어요.'
            : '현재 위치 확인 없이 안전도장을 준비했어요.',
        rssi: 0,
        location: _placeholderLocation(),
      );
    }

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

    final localAlias = _buildAdvertisedAlias(
      promiseId: promiseId,
      userId: currentUserId,
    );
    final partnerAlias = _buildAdvertisedAlias(
      promiseId: promiseId,
      userId: partnerUserId,
    );

    StreamSubscription<List<ScanResult>>? scanSubscription;

    try {
      await _startAdvertising(localAlias);

      final resultCompleter = Completer<int?>();
      scanSubscription = FlutterBluePlus.onScanResults.listen((results) {
        for (final result in results) {
          final advertisedName = result.advertisementData.advName.trim();
          if (advertisedName != partnerAlias) continue;

          if (!resultCompleter.isCompleted) {
            resultCompleter.complete(result.rssi);
          }
          return;
        }
      });
      FlutterBluePlus.cancelWhenScanComplete(scanSubscription);

      await FlutterBluePlus.startScan(
        withServices: [Guid(_serviceUuid)],
        withNames: [partnerAlias],
        timeout: _scanTimeout,
        androidUsesFineLocation: true,
      );

      final rssi = await resultCompleter.future.timeout(
        _scanTimeout,
        onTimeout: () => null,
      );

      if (!_disableNearbyRequirement &&
          (rssi == null || rssi < _nearbyRssiThreshold)) {
        return SafetyStampVerificationResult.failure(
          failure: SafetyStampVerificationFailure.partnerNotNearby,
          message: '상대방이 충분히 가까이 있어야 안전도장을 찍을 수 있어요. 휴대폰을 더 가까이 두고 다시 시도해주세요.',
        );
      }

      return SafetyStampVerificationResult.success(
        message: _disableNearbyRequirement
            ? '상대 거리 확인 없이 안전도장을 준비했어요.'
            : '근처에서 상대방이 확인되어 안전도장을 준비했어요.',
        rssi: rssi ?? 0,
        location: _placeholderLocation(),
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
    if (adapterState == BluetoothAdapterState.on) {
      return null;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
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

    if (await _peripheral.isBluetoothOn) {
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

  Future<void> _startAdvertising(String localAlias) async {
    final advertiseData = AdvertiseData(
      serviceUuid: _serviceUuid,
      localName: localAlias,
    );

    await _peripheral.stop();
    await _peripheral.start(advertiseData: advertiseData);
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
  }) {
    final digest = sha1.convert('$promiseId::$userId'.codeUnits).toString();
    return 'SYN${digest.substring(0, _maxAdvertisedNameLength - 3)}';
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

  SafetyStampLocationSnapshot _placeholderLocation() {
    return SafetyStampLocationSnapshot(
      latitude: 0,
      longitude: 0,
      accuracyMeters: 0,
      capturedAt: DateTime.now(),
    );
  }
}
