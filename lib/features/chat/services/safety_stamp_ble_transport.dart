import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_ble_peripheral/flutter_ble_peripheral.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

/// The platform Bluetooth LE operations the safety-stamp proximity check
/// needs. The service owns the lifecycle (who advertises, for how long);
/// this seam only talks to the radio, so the lifecycle is unit-testable.
abstract class SafetyStampBleTransport {
  Future<bool> isSupported();

  /// Whether the Bluetooth permissions are already granted. Never prompts.
  Future<bool> hasPermission();

  /// Asks the user for the Bluetooth permissions.
  Future<bool> requestPermission();

  /// Whether the adapter is on right now. Never prompts.
  Future<bool> isBluetoothOn();

  /// Waits for the adapter and, on Android, asks the user to turn it on.
  Future<bool> ensureBluetoothOn();

  /// Starts (or replaces) the advertisement. Returns whether the platform
  /// reports it as running.
  Future<bool> startAdvertising({
    required String serviceUuid,
    required String localName,
  });

  Future<bool> isAdvertising();
  Future<void> stopAdvertising();

  /// Scans for the partner's advertisement and emits the RSSI of every
  /// matching sighting until [timeout] or [stopScan].
  Stream<int> scanForPartner({
    required String partnerServiceUuid,
    required String legacyServiceUuid,
    required Set<String> partnerNames,
    required Duration timeout,
  });

  Future<void> stopScan();
}

/// flutter_ble_peripheral (advertising) + flutter_blue_plus (scanning).
class FlutterSafetyStampBleTransport implements SafetyStampBleTransport {
  FlutterSafetyStampBleTransport({FlutterBlePeripheral? peripheral})
    : _peripheral = peripheral ?? FlutterBlePeripheral();

  final FlutterBlePeripheral _peripheral;

  static const Duration _advertisingReadyTimeout = Duration(seconds: 3);
  static const Duration _peripheralReadyTimeout = Duration(seconds: 5);

  @override
  Future<bool> isSupported() async => FlutterBluePlus.isSupported;

  bool _isGrantedPermissionState(BluetoothPeripheralState state) {
    return state == BluetoothPeripheralState.granted ||
        state == BluetoothPeripheralState.ready ||
        state == BluetoothPeripheralState.limited;
  }

  @override
  Future<bool> hasPermission() async {
    return _isGrantedPermissionState(await _peripheral.hasPermission());
  }

  @override
  Future<bool> requestPermission() async {
    return _isGrantedPermissionState(await _peripheral.requestPermission());
  }

  @override
  Future<bool> isBluetoothOn() => _peripheral.isBluetoothOn;

  @override
  Future<bool> ensureBluetoothOn() async {
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

    final deadline = DateTime.now().add(_peripheralReadyTimeout);
    while (DateTime.now().isBefore(deadline)) {
      if (await _peripheral.isBluetoothOn) return true;
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    return false;
  }

  @override
  Future<bool> startAdvertising({
    required String serviceUuid,
    required String localName,
  }) async {
    final advertiseData = AdvertiseData(
      serviceUuid: serviceUuid,
      localName: localName,
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

  @override
  Future<bool> isAdvertising() => _peripheral.isAdvertising;

  @override
  Future<void> stopAdvertising() => _peripheral.stop();

  @override
  Stream<int> scanForPartner({
    required String partnerServiceUuid,
    required String legacyServiceUuid,
    required Set<String> partnerNames,
    required Duration timeout,
  }) {
    final partnerServiceGuid = Guid(partnerServiceUuid);
    late final StreamController<int> controller;
    StreamSubscription<List<ScanResult>>? subscription;

    controller = StreamController<int>(
      onListen: () async {
        subscription = FlutterBluePlus.onScanResults.listen((results) {
          for (final result in results) {
            final advertisement = result.advertisementData;
            final hasPartnerService = advertisement.serviceUuids.any(
              (service) => service == partnerServiceGuid,
            );

            if (!hasPartnerService) {
              // Legacy devices advertised the fixed UUID and relied on the
              // device name as the second half of the handshake.
              final advertisedName = advertisement.advName.trim();
              if (!partnerNames.contains(advertisedName)) continue;
            }

            if (!controller.isClosed) controller.add(result.rssi);
          }
        }, onError: controller.addError);
        try {
          await FlutterBluePlus.startScan(
            // The new per-user UUID is the primary identity and works on
            // both platforms. The fixed UUID remains in the filter for old
            // builds. Do not use withNames: iOS may omit or normalize local
            // names.
            withServices: [partnerServiceGuid, Guid(legacyServiceUuid)],
            timeout: timeout,
            androidUsesFineLocation: true,
          );
        } catch (error, stackTrace) {
          if (!controller.isClosed) controller.addError(error, stackTrace);
        }
      },
      onCancel: () async {
        await subscription?.cancel();
      },
    );
    return controller.stream;
  }

  @override
  Future<void> stopScan() async {
    if (FlutterBluePlus.isScanningNow) {
      await FlutterBluePlus.stopScan();
    }
  }
}
