import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/chat/models/safety_stamp_verification.dart';
import 'package:seolleyeon/features/chat/services/safety_stamp_ble_transport.dart';
import 'package:seolleyeon/features/chat/services/safety_stamp_verification_service.dart';

// AUD-06: the safety-stamp proximity check must not deadlock when the two
// users do not tap at the same moment.
//
// LOGIC VERIFIED WITH FAKES / TWO-DEVICE NOT VERIFIED: the radio is a fake
// shared "air"; real Bluetooth behaviour is not exercised here.

/// What is currently on air, shared by the simulated devices.
class _Air {
  final Set<_FakeTransport> _advertisers = {};
  final StreamController<void> _changed = StreamController<void>.broadcast(
    sync: true,
  );

  void update() => _changed.add(null);

  bool isOnAir(String serviceUuid) => _advertisers.any(
    (device) => device.advertising && device.serviceUuid == serviceUuid,
  );
}

class _FakeTransport implements SafetyStampBleTransport {
  _FakeTransport(this._air) {
    _air._advertisers.add(this);
  }

  final _Air _air;
  bool supported = true;
  bool permissionGranted = true;
  bool grantOnRequest = true;
  bool bluetoothOn = true;
  bool advertising = false;
  String? serviceUuid;

  /// RSSI this device measures for the partner.
  int measuredRssi = -60;
  List<int>? rssiSamples;

  int permissionPrompts = 0;
  int bluetoothPrompts = 0;
  int startCalls = 0;
  int stopCalls = 0;
  int activeScans = 0;

  @override
  Future<bool> isSupported() async => supported;

  @override
  Future<bool> hasPermission() async => permissionGranted;

  @override
  Future<bool> requestPermission() async {
    permissionPrompts += 1;
    permissionGranted = grantOnRequest;
    return permissionGranted;
  }

  @override
  Future<bool> isBluetoothOn() async => bluetoothOn;

  @override
  Future<bool> ensureBluetoothOn() async {
    if (!bluetoothOn) bluetoothPrompts += 1;
    return bluetoothOn;
  }

  @override
  Future<bool> startAdvertising({
    required String serviceUuid,
    required String localName,
  }) async {
    startCalls += 1;
    if (!bluetoothOn || !permissionGranted) return false;
    this.serviceUuid = serviceUuid;
    advertising = true;
    _air.update();
    return true;
  }

  @override
  Future<bool> isAdvertising() async => advertising;

  @override
  Future<void> stopAdvertising() async {
    stopCalls += 1;
    advertising = false;
    _air.update();
  }

  /// The OS silently drops the advertisement (backgrounding, radio reset).
  void dropAdvertisement() {
    advertising = false;
    _air.update();
  }

  @override
  Stream<int> scanForPartner({
    required String partnerServiceUuid,
    required String legacyServiceUuid,
    required Set<String> partnerNames,
    required Duration timeout,
  }) {
    late final StreamController<int> controller;
    StreamSubscription<void>? airSubscription;
    void report() {
      if (controller.isClosed || !_air.isOnAir(partnerServiceUuid)) return;
      for (final sample in rssiSamples ?? [measuredRssi]) {
        controller.add(sample);
      }
    }

    controller = StreamController<int>(
      onListen: () {
        activeScans += 1;
        airSubscription = _air._changed.stream.listen((_) => report());
        report();
      },
      // `async` on purpose: the returned future must belong to the test's
      // fake-async zone. A plain subscription cancel returns a root-zone
      // future, and awaiting that inside testWidgets never resumes.
      onCancel: () async {
        activeScans -= 1;
        unawaited(airSubscription?.cancel());
      },
    );
    return controller.stream;
  }

  @override
  Future<void> stopScan() async {}
}

class _Device {
  _Device(_Air air, this.userId, this.partnerId)
    : transport = _FakeTransport(air),
      presence = SafetyStampPresence.detached() {
    service = SafetyStampVerificationService(
      transport: transport,
      presence: presence,
      captureLocation: () async => SafetyStampVerificationResult.success(
        message: 'ok',
        rssi: 0,
        location: SafetyStampLocationSnapshot(
          latitude: 37.56,
          longitude: 126.93,
          accuracyMeters: 5,
          capturedAt: DateTime(2026, 11, 21),
        ),
      ),
    );
  }

  static const promiseId = 'promise-1';

  final String userId;
  final String partnerId;
  final _FakeTransport transport;
  final SafetyStampPresence presence;
  late final SafetyStampVerificationService service;

  Future<bool> openScreen() =>
      service.startPresence(promiseId: promiseId, currentUserId: userId);

  /// Taps "stamp" and waits for the result, advancing the fake clock past
  /// the scan window when the partner is not found.
  Future<SafetyStampVerificationResult> stamp(WidgetTester tester) async {
    SafetyStampVerificationResult? result;
    Object? error;
    unawaited(
      service
          .verifyNearbyAndCaptureLocation(
            promiseId: promiseId,
            currentUserId: userId,
            partnerUserId: partnerId,
          )
          .then<void>(
            (value) => result = value,
            onError: (Object e, StackTrace st) {
              error = e;
              debugPrint('stamp error: $e');
              debugPrint('$st');
            },
          ),
    );
    for (var i = 0; i < 10 && result == null && error == null; i++) {
      await tester.pump(const Duration(seconds: 1));
    }
    if (error != null) fail('attempt threw: $error');
    return result!;
  }
}

void main() {
  late _Air air;
  late _Device a;
  late _Device b;

  setUp(() {
    air = _Air();
    a = _Device(air, 'user-a', 'user-b');
    b = _Device(air, 'user-b', 'user-a');
  });

  Future<void> releaseAll() async {
    await a.presence.resetForTest();
    await b.presence.resetForTest();
  }

  testWidgets('A first, then B: A stays discoverable after its own attempt', (
    tester,
  ) async {
    // B is not on the stamp screen yet, so A cannot find B.
    final first = await a.stamp(tester);
    expect(first.failure, SafetyStampVerificationFailure.partnerNotNearby);
    expect(
      a.transport.advertising,
      isTrue,
      reason: 'the old code stopped advertising in the attempt\'s finally',
    );

    // B taps a minute later and finds A.
    await tester.pump(const Duration(minutes: 1));
    final second = await b.stamp(tester);
    expect(second.isSuccess, isTrue);
    expect(b.transport.advertising, isTrue, reason: 'B stays discoverable');

    // A retries and now finds B: the phase completes for both.
    final third = await a.stamp(tester);
    expect(third.isSuccess, isTrue);
    await releaseAll();
  });

  testWidgets('one side already stamped: the other can still find it later', (
    tester,
  ) async {
    await b.openScreen();
    final aResult = await a.stamp(tester);
    expect(aResult.isSuccess, isTrue);

    // B's first tap fails for an unrelated reason (too far away).
    b.transport.measuredRssi = -95;
    expect(
      (await b.stamp(tester)).failure,
      SafetyStampVerificationFailure.partnerNotNearby,
    );

    // B moves closer and retries several minutes after A finished.
    await tester.pump(const Duration(minutes: 5));
    b.transport.measuredRssi = -60;
    final retry = await b.stamp(tester);
    expect(
      retry.isSuccess,
      isTrue,
      reason: 'A must still be advertising after its own success',
    );
    await releaseAll();
  });

  testWidgets('both screens open: a single tap each is enough, in any order', (
    tester,
  ) async {
    expect(await a.openScreen(), isTrue);
    expect(await b.openScreen(), isTrue);
    expect(a.transport.permissionPrompts, 0);

    expect((await b.stamp(tester)).isSuccess, isTrue);
    expect((await a.stamp(tester)).isSuccess, isTrue);
    await releaseAll();
  });

  testWidgets('simultaneous taps succeed on both sides', (tester) async {
    SafetyStampVerificationResult? aResult;
    SafetyStampVerificationResult? bResult;
    unawaited(
      a.service
          .verifyNearbyAndCaptureLocation(
            promiseId: _Device.promiseId,
            currentUserId: 'user-a',
            partnerUserId: 'user-b',
          )
          .then((value) => aResult = value),
    );
    unawaited(
      b.service
          .verifyNearbyAndCaptureLocation(
            promiseId: _Device.promiseId,
            currentUserId: 'user-b',
            partnerUserId: 'user-a',
          )
          .then((value) => bResult = value),
    );
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();

    expect(aResult?.isSuccess, isTrue);
    expect(bResult?.isSuccess, isTrue);
    expect(a.transport.activeScans, 0);
    expect(b.transport.activeScans, 0);
    await releaseAll();
  });

  testWidgets('a weak first sighting does not fail the attempt', (
    tester,
  ) async {
    await b.openScreen();
    a.transport.rssiSamples = [-92, -85, -64];
    final result = await a.stamp(tester);
    expect(result.isSuccess, isTrue);
    expect(result.rssi, -64);
    await releaseAll();
  });

  testWidgets('the presence is bounded: it ends by itself', (tester) async {
    await a.stamp(tester);
    expect(a.transport.advertising, isTrue);

    await tester.pump(
      SafetyStampPresence.holdDuration - const Duration(seconds: 30),
    );
    expect(a.transport.advertising, isTrue);

    await tester.pump(const Duration(minutes: 1));
    await tester.pump();
    expect(a.transport.advertising, isFalse);
    expect(a.presence.isHeld, isFalse);
  });

  testWidgets('phase complete for both: advertising stops at once', (
    tester,
  ) async {
    await a.openScreen();
    await b.openScreen();
    await a.stamp(tester);
    await b.stamp(tester);

    await a.service.completePresence();
    await b.service.completePresence();
    expect(a.transport.advertising, isFalse);
    expect(b.transport.advertising, isFalse);

    // No timer is left behind to stop a later presence.
    await tester.pump(SafetyStampPresence.holdDuration * 2);
    expect(a.transport.stopCalls, 1);
  });

  testWidgets('a new screen takes over the presence instead of restarting '
      'or duplicating it', (tester) async {
    await a.openScreen();
    final starts = a.transport.startCalls;

    final reopened = SafetyStampVerificationService(
      transport: a.transport,
      presence: a.presence,
    );
    expect(
      await reopened.startPresence(
        promiseId: _Device.promiseId,
        currentUserId: 'user-a',
      ),
      isTrue,
    );
    expect(a.transport.startCalls, starts, reason: 'already on air');

    // A different promise replaces the advertised identity.
    final firstIdentity = a.presence.heldServiceUuid;
    await reopened.startPresence(
      promiseId: 'promise-2',
      currentUserId: 'user-a',
    );
    expect(a.presence.heldServiceUuid, isNot(firstIdentity));
    expect(a.transport.serviceUuid, a.presence.heldServiceUuid);
    await releaseAll();
  });

  testWidgets('permission denied: no silent start, the attempt reports it, '
      'and granting later recovers', (tester) async {
    a.transport
      ..permissionGranted = false
      ..grantOnRequest = false;
    expect(await a.openScreen(), isFalse);
    expect(a.transport.permissionPrompts, 0, reason: 'opening never prompts');
    expect(a.transport.advertising, isFalse);

    final denied = await a.stamp(tester);
    expect(
      denied.failure,
      SafetyStampVerificationFailure.bluetoothPermissionDenied,
    );
    expect(a.transport.permissionPrompts, 1);
    expect(a.transport.advertising, isFalse);

    a.transport.grantOnRequest = true;
    await b.openScreen();
    expect((await a.stamp(tester)).isSuccess, isTrue);
    await releaseAll();
  });

  testWidgets('bluetooth off: reported, nothing left on air', (tester) async {
    a.transport.bluetoothOn = false;
    expect(await a.openScreen(), isFalse);
    final result = await a.stamp(tester);
    expect(result.failure, SafetyStampVerificationFailure.bluetoothOff);
    expect(a.presence.isHeld, isFalse);
  });

  testWidgets('backgrounding keeps the presence; a dropped advertisement is '
      'put back on resume', (tester) async {
    await a.stamp(tester);
    expect(a.transport.advertising, isTrue);

    a.presence.didChangeAppLifecycleState(AppLifecycleState.paused);
    expect(a.transport.advertising, isTrue, reason: 'B may be stamping now');
    expect(a.presence.isHeld, isTrue);

    // The OS dropped it while suspended.
    a.transport.dropAdvertisement();
    a.presence.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pump();
    expect(a.transport.advertising, isTrue);

    // B, who was waiting, now finds A again.
    expect((await b.stamp(tester)).isSuccess, isTrue);
    await releaseAll();
  });

  testWidgets('partner disconnects midway: clean failure, then reconnect '
      'succeeds', (tester) async {
    await b.openScreen();
    // B's radio goes away before A scans.
    b.transport.dropAdvertisement();
    final lost = await a.stamp(tester);
    expect(lost.failure, SafetyStampVerificationFailure.partnerNotNearby);
    expect(a.transport.activeScans, 0);
    expect(a.transport.advertising, isTrue);

    // B comes back (app resumed) and A retries.
    await b.presence.reassert();
    expect(b.transport.advertising, isTrue);
    expect((await a.stamp(tester)).isSuccess, isTrue);
    await releaseAll();
  });

  testWidgets('a resume after the hold expired does not restart it', (
    tester,
  ) async {
    await a.stamp(tester);
    await tester.pump(
      SafetyStampPresence.holdDuration + const Duration(seconds: 1),
    );
    await tester.pump();
    expect(a.transport.advertising, isFalse);

    final starts = a.transport.startCalls;
    await a.presence.reassert();
    expect(a.transport.startCalls, starts);
  });

  test('the presence hold is short enough to bound battery and exposure', () {
    final source = SafetyStampPresence.holdDuration;
    expect(source, lessThanOrEqualTo(const Duration(minutes: 15)));
  });

  testWidgets('the advertised identity differs per promise and per user', (
    tester,
  ) async {
    await a.openScreen();
    await b.openScreen();
    final aFirst = a.presence.heldServiceUuid!;
    final bFirst = b.presence.heldServiceUuid!;
    expect(aFirst, isNot(bFirst));
    expect(aFirst, isNot(contains('user-a')));
    expect(
      RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      ).hasMatch(aFirst),
      isTrue,
    );

    await a.service.startPresence(
      promiseId: 'another-promise',
      currentUserId: 'user-a',
    );
    expect(a.presence.heldServiceUuid, isNot(aFirst));
    await releaseAll();
  });
}
