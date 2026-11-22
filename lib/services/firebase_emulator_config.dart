import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:cloud_functions/cloud_functions.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter/foundation.dart' show debugPrint;

import 'firebase_runtime.dart';

/// Local Emulator Suite ports. They must match the `emulators` block of
/// firebase.json (test/firebase_emulator_config_test.dart pins that).
class FirebaseEmulatorPorts {
  const FirebaseEmulatorPorts._();

  static const int auth = 9099;
  static const int firestore = 8080;
  static const int functions = 5001;
  static const int storage = 9199;
}

/// Seam over the FlutterFire "use emulator" calls, one method per backend
/// service the client reads or writes.
abstract class FirebaseEmulatorBinder {
  Future<void> bindAuth(String host, int port);
  Future<void> bindFirestore(String host, int port);
  Future<void> bindFunctions(String host, int port);
  Future<void> bindStorage(String host, int port);
}

/// Thrown when only part of the emulator routing could be applied. The
/// process then talks to the emulator for some services and to the
/// production project for the rest, so start-up must not continue.
class FirebaseEmulatorRoutingError extends StateError {
  FirebaseEmulatorRoutingError({required this.bound, required this.failed})
    : super(
        'Firebase emulator routing is incomplete '
        '(bound: ${bound.join(', ')}; failed: $failed). '
        'Refusing to start with production and emulator services mixed.',
      );

  final List<String> bound;
  final String failed;
}

/// A release build never talks to an emulator, whatever defines it was
/// compiled with.
bool shouldUseFirebaseEmulators({
  required bool requested,
  required bool isReleaseBuild,
}) {
  return requested && !isReleaseBuild;
}

/// Routes EVERY Firebase backend service to the local Emulator Suite, or none
/// of them.
///
/// Before this existed Auth, Firestore and Functions were routed but Storage
/// was not, so an emulator run still read the production bucket. A binding
/// that throws is not swallowed either: the routing cannot be undone, so the
/// caller must abort start-up ([FirebaseEmulatorRoutingError]) instead of
/// running half against production.
///
/// Returns whether the emulators are in use.
Future<bool> configureFirebaseEmulators({
  required bool requested,
  required bool isReleaseBuild,
  required String host,
  FirebaseEmulatorBinder binder = const FlutterFireEmulatorBinder(),
}) async {
  if (!shouldUseFirebaseEmulators(
    requested: requested,
    isReleaseBuild: isReleaseBuild,
  )) {
    return false;
  }

  final emulatorHost = host.trim();
  if (emulatorHost.isEmpty) {
    throw FirebaseEmulatorRoutingError(bound: const [], failed: 'host');
  }

  final steps = <String, Future<void> Function()>{
    'auth': () => binder.bindAuth(emulatorHost, FirebaseEmulatorPorts.auth),
    'firestore': () =>
        binder.bindFirestore(emulatorHost, FirebaseEmulatorPorts.firestore),
    'functions': () =>
        binder.bindFunctions(emulatorHost, FirebaseEmulatorPorts.functions),
    'storage': () =>
        binder.bindStorage(emulatorHost, FirebaseEmulatorPorts.storage),
  };

  final bound = <String>[];
  for (final step in steps.entries) {
    try {
      await step.value();
    } catch (_) {
      throw FirebaseEmulatorRoutingError(bound: bound, failed: step.key);
    }
    bound.add(step.key);
  }

  debugPrint(
    '[Firebase] Using local emulators (${bound.join('/')}) '
    'host=$emulatorHost',
  );
  return true;
}

class FlutterFireEmulatorBinder implements FirebaseEmulatorBinder {
  const FlutterFireEmulatorBinder();

  @override
  Future<void> bindAuth(String host, int port) {
    return FirebaseAuth.instance.useAuthEmulator(host, port);
  }

  @override
  Future<void> bindFirestore(String host, int port) async {
    FirebaseFirestore.instance.useFirestoreEmulator(host, port);
  }

  @override
  Future<void> bindFunctions(String host, int port) async {
    // Both the default instance and the Seoul instance every callable uses
    // (see firebaseFunctionsRegion).
    FirebaseFunctions.instance.useFunctionsEmulator(host, port);
    FirebaseFunctions.instanceFor(
      region: firebaseFunctionsRegion,
    ).useFunctionsEmulator(host, port);
  }

  @override
  Future<void> bindStorage(String host, int port) {
    return FirebaseStorage.instance.useStorageEmulator(host, port);
  }
}
