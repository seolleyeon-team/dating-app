import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/profile/widgets/friend_invite_confirmation_sheet.dart';

/// The confirmation step between an external link and any friendship
/// mutation. AuthProvider only calls acceptFriendInvite when this returns
/// exactly `true`; `false` is "나중에"; `null` is reserved for "the route was
/// removed underneath the sheet" (cold-start splash reset) and keeps the
/// invite pending.
void main() {
  const title = '에이님을 친구로 추가할까요?';

  /// Pumps a host app, opens the sheet and returns its (unawaited) result.
  Future<Future<bool?>> openSheet(
    WidgetTester tester, {
    GlobalKey<NavigatorState>? navigatorKey,
  }) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      CupertinoApp(
        navigatorKey: navigatorKey,
        onGenerateRoute: (settings) => CupertinoPageRoute<void>(
          settings: settings,
          builder: (context) {
            hostContext = context;
            return const CupertinoPageScaffold(child: SizedBox.expand());
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    final result = showFriendInviteConfirmationSheet(
      hostContext,
      inviterName: '에이',
    );
    await tester.pumpAndSettle();
    return result;
  }

  testWidgets('shows who is being added and two explicit choices', (
    tester,
  ) async {
    await openSheet(tester);
    expect(find.text(title), findsOneWidget);
    expect(
      find.text(FriendInviteConfirmationSheet.confirmLabel),
      findsOneWidget,
    );
    expect(find.text(FriendInviteConfirmationSheet.laterLabel), findsOneWidget);
  });

  testWidgets('[친구 추가] resolves true', (tester) async {
    final result = await openSheet(tester);
    await tester.tap(find.byKey(const Key('friend_invite_confirm_button')));
    await tester.pumpAndSettle();
    expect(await result, isTrue);
  });

  testWidgets('[나중에] resolves false (no mutation, no re-prompt)', (
    tester,
  ) async {
    final result = await openSheet(tester);
    await tester.tap(find.byKey(const Key('friend_invite_later_button')));
    await tester.pumpAndSettle();
    expect(await result, isFalse);
  });

  testWidgets('tapping outside does not dismiss: a decision is required', (
    tester,
  ) async {
    await openSheet(tester);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.text(title), findsOneWidget);
  });

  testWidgets('a route reset underneath the sheet yields null, never true', (
    tester,
  ) async {
    final navigatorKey = GlobalKey<NavigatorState>();
    final result = await openSheet(tester, navigatorKey: navigatorKey);
    expect(find.text(title), findsOneWidget);

    // What SplashScreen does when it lands on main.
    navigatorKey.currentState!.pushNamedAndRemoveUntil('/main', (_) => false);
    await tester.pumpAndSettle();

    expect(await result, isNull);
    expect(find.text(title), findsNothing);
  });
}
