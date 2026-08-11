import 'package:flutter/material.dart';

import '../../../router/route_names.dart';

bool _isBlindMeetingFlowAnchor(Route<dynamic> route) {
  final name = route.settings.name;
  return name == RouteNames.main ||
      name == RouteNames.event ||
      name == RouteNames.blindTasteMeeting ||
      RouteNames.legacyBlindMeetingAliases.contains(name);
}

/// Clears transient DNA/schedule layers before showing the canonical Waiting.
void pushBlindMeetingWaitingAndClearTransientStack(BuildContext context) {
  Navigator.of(context, rootNavigator: true).pushNamedAndRemoveUntil(
    RouteNames.blindTasteMeetingWaiting,
    _isBlindMeetingFlowAnchor,
  );
}

/// Returns to an existing Intro route when possible, otherwise creates one.
///
/// A direct/deep-linked Waiting route may be the first route, so replacing it
/// is required in that case. When the app was entered from the main/event
/// shell, that parent route remains underneath Intro.
void returnToBlindMeetingIntro(BuildContext context) {
  final navigator = Navigator.of(context, rootNavigator: true);
  var foundIntro = false;
  var foundParent = false;

  navigator.popUntil((route) {
    final name = route.settings.name;
    if (name == RouteNames.blindTasteMeeting) {
      foundIntro = true;
      return true;
    }
    if (name == RouteNames.main || name == RouteNames.event) {
      foundParent = true;
      return true;
    }
    return route.isFirst;
  });

  if (foundIntro) return;
  if (foundParent) {
    navigator.pushNamed(RouteNames.blindTasteMeeting);
    return;
  }
  navigator.pushReplacementNamed(RouteNames.blindTasteMeeting);
}
