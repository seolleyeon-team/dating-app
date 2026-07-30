import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'route_names.dart';

// Splash & Auth (로그인 화면 없음: /login → 카카오 인증 화면으로 통일)
import '../features/splash/splash_screen.dart';
import '../features/auth/screens/adult_verification_gate_screen.dart';
import '../features/auth/screens/kakao_auth_screen.dart';
import '../features/auth/screens/student_verification_screen.dart';
import '../screens/auth/kakao_callback_screen.dart';
import '../features/onboarding/screens/terms_screen.dart';

// Onboarding
import '../features/onboarding/screens/basic_info_screen.dart';
import '../features/onboarding/screens/interests_screen.dart';
import '../features/onboarding/screens/interests_selection_screen.dart';
import '../features/onboarding/screens/lifestyle_screen.dart';
import '../features/onboarding/screens/major_selection_screen.dart';
import '../features/onboarding/screens/department_screen.dart';
import '../features/onboarding/screens/photo_upload_screen.dart';
import '../features/onboarding/screens/self_introduction_screen.dart';
import '../features/onboarding/screens/profile_qa_screen.dart';
import '../features/onboarding/screens/keyword_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_type_screen.dart';
import '../features/onboarding/screens/height_selection_screen.dart';
import '../features/onboarding/screens/ideal_height_range_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_age_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_height_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_mbti_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_department_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_personality_screen.dart';
import '../features/onboarding/screens/ideal_type/ideal_lifestyle_screen.dart';

// Tutorial
import '../features/tutorial/screens/welcome_tutorial_screen.dart';
import '../features/tutorial/screens/tutorial_screen.dart';
import '../features/tutorial/screens/todays_match_tutorial_screen.dart';
import '../features/tutorial/screens/ai_taste_button_tutorial_screen.dart';
import '../features/tutorial/screens/ai_taste_training_screen.dart';
import '../features/tutorial/screens/ai_taste_training_tutorial_screen.dart';
import '../features/tutorial/screens/slot_machine_tutorial_screen.dart';
import '../features/tutorial/screens/promise_agreement_tutorial_screen.dart';
import '../features/tutorial/screens/season_meeting_intro_screen.dart';
import '../features/tutorial/screens/bamboo_forest_intro_tutorial_screen.dart';
import '../features/tutorial/screens/bamboo_forest_safety_tutorial_screen.dart';
import '../features/tutorial/screens/bamboo_forest_write_tutorial_screen.dart';

// Main & Tabs
import '../shared/layouts/main_scaffold.dart';

// Matching
import '../features/matching/screens/mystery_card_screen.dart';
import '../features/matching/screens/profile_discovery_screen.dart';
import '../features/matching/screens/profile_card_screen.dart';
import '../features/matching/screens/ai_preference_screen.dart';
import '../features/matching/screens/ai_match_card_screen.dart';
import '../features/matching/screens/profile_specific_detail_screen.dart';
import '../shared/widgets/sensitive_screen_protection.dart';

// Chat
import '../features/chat/screens/premium_chat_list_screen.dart';
import '../features/chat/screens/chat_room_screen.dart';
import '../features/chat/screens/group_match_screen.dart';
import '../features/chat/models/chat_room_data.dart';
import '../features/chat/models/safety_stamp_follow_up_args.dart';
import '../features/chat/screens/safety_stamp_follow_up_screen.dart';

// Community
import '../features/community/screens/community_screen.dart';
import '../features/community/screens/post_detail_screen.dart';
import '../features/community/screens/post_write_screen.dart';

// Profile
import '../features/profile/screens/my_page_screen.dart';
import '../features/profile/screens/heart_charge_screen.dart';
import '../features/profile/screens/friends_list_screen.dart';
import '../features/profile/screens/profile_edit_screen.dart';
import '../features/profile/screens/received_hearts_screen.dart';
import '../features/matching/screens/sent_hearts_screen.dart';
import '../features/profile/screens/asks_inbox_screen.dart';
import '../features/profile/screens/settings_screen.dart';
import '../features/profile/screens/account_management_screen.dart';
import '../features/profile/screens/notification_settings_screen.dart';
import '../features/profile/screens/safety_stamp_log_screen.dart';
import '../features/profile/screens/contact_block_screen.dart';
import '../features/profile/screens/kakao_friend_message_test_screen.dart';
import '../features/matching/models/profile_card_args.dart';
import '../features/profile/screens/terms_webview_screen.dart';
import '../features/profile/screens/faq_screen.dart';
import '../features/reports/issue_report_screen.dart';
import '../services/issue_report_service.dart';
import '../features/reports/inquiry_screen.dart';
import '../services/inquiry_service.dart';

// Notifications
import '../features/notifications/screens/notification_list_screen.dart';

// Event
import '../features/event/screens/event_screen.dart';
import '../features/event/screens/add_friend.dart';
import '../features/event/screens/team_setup_screen.dart';
import '../features/event/screens/team_friend_picker_screen.dart';
import '../features/event/screens/event_team_invite_response_screen.dart';
import '../features/event/models/event_team_route_args.dart';
import '../features/event/screens/season_meeting_roulette_screen.dart';
import '../features/event/screens/match_result_screen.dart';
import '../features/event/screens/random_matching_screen1.dart';
import '../features/event/screens/random_mathcing_screen.dart';
import '../features/event/screens/random_meeting_screen.dart';
import '../features/event/screens/three_vs_three_match_screen.dart';
import '../features/event/screens/team_requests_screen.dart';
import '../features/event/screens/team_request_declined_screen.dart';

// Meeting
import '../features/meeting/screens/meeting_application_screen.dart';

import '../shared/layouts/main_scaffold_args.dart';
import '../services/auth_service.dart';
import '../services/storage_service.dart';

const bool _showKakaoReviewTools =
    kDebugMode || bool.fromEnvironment('KAKAO_REVIEW_TOOLS');

/// 앱 라우터 (CupertinoPageRoute, 흐름도 단일 소스)
class AppRouter {
  static Route<dynamic> generateRoute(RouteSettings settings) {
    final name = settings.name ?? '';

    // 카카오 OAuth 콜백: 앱이 /?code=... 로 열렸을 때 (iOS/Android 딥링크)
    if (name.contains('code=') || name.startsWith('/?')) {
      return _cupertino(KakaoCallbackScreen(callbackPathAndQuery: name));
    }

    switch (name) {
      // Auth
      case RouteNames.splash:
        return _cupertino(const SplashScreen());
      case RouteNames.login:
      case RouteNames.kakaoAuth:
        return _cupertino(const KakaoAuthScreen());
      case RouteNames.terms:
        return _cupertino(const TermsScreen());
      case RouteNames.adultVerification:
        return _cupertino(const AdultVerificationGateScreen());
      case RouteNames.studentVerification:
        return _cupertino(const StudentVerificationScreen());

      // Onboarding
      case RouteNames.onboardingBasicInfo:
        return _cupertino(const BasicInfoScreen());
      case RouteNames.onboardingInterestsSelection:
        return _cupertino(const InterestsSelectionScreen());
      case RouteNames.onboardingLifestyle:
        return _cupertino(const LifestyleScreen());
      case RouteNames.onboardingMajor:
        return _cupertino(const MajorSelectionScreen());
      case RouteNames.onboardingDepartment:
        {
          final args = settings.arguments;
          final initialMajor = args is Map<String, dynamic>
              ? args['major']?.toString()
              : args is String
              ? args
              : null;
          return _cupertino(DepartmentScreen(initialMajor: initialMajor));
        }
      case RouteNames.onboardingPhoto:
        return _cupertino(const PhotoUploadScreen());
      case RouteNames.onboardingSelfIntro:
        return _cupertino(const SelfIntroductionScreen());
      case RouteNames.onboardingProfileQa:
        return _cupertino(const ProfileQaScreen());
      case RouteNames.onboardingKeywords:
        return _cupertino(const KeywordScreen());
      case RouteNames.onboardingIdealType:
        return _cupertino(const IdealTypeScreen());
      case RouteNames.onboardingHeightSelection:
        {
          final args = settings.arguments as Map<String, dynamic>?;
          final initialHeight = args?['initialHeight'] as int? ?? 175;
          return _cupertino(
            HeightSelectionScreen(initialHeight: initialHeight.clamp(140, 200)),
          );
        }
      case RouteNames.onboardingIdealHeightRange:
        return _cupertino(const IdealHeightRangeScreen());
      case RouteNames.onboardingIdealAge:
        return _cupertino(const IdealAgeScreen());
      case RouteNames.onboardingIdealHeight:
        return _cupertino(const IdealHeightScreen());
      case RouteNames.onboardingIdealMbti:
        return _cupertino(const IdealMbtiScreen());
      case RouteNames.onboardingIdealDepartment:
        return _cupertino(const IdealDepartmentScreen());
      case RouteNames.onboardingIdealPersonality:
        return _cupertino(const IdealPersonalityScreen());
      case RouteNames.onboardingIdealLifestyle:
        return _cupertino(const IdealLifestyleScreen());
      case RouteNames.onboardingInterests:
        return _cupertino(const InterestsScreen());

      // Tutorial
      case RouteNames.welcomeTutorial:
        return _cupertino(const WelcomeTutorialScreen());
      case RouteNames.tutorial:
        return _cupertino(const TutorialScreen());
      case RouteNames.todaysMatchTutorial:
        return _cupertino(const TodaysMatchTutorialScreen());
      case RouteNames.aiTasteButtonTutorial:
        return _cupertino(const AiTasteButtonTutorialScreen());
      case RouteNames.aiTasteTraining:
        return _cupertino(const AiTasteTrainingScreen());
      case RouteNames.aiTasteTrainingTutorial:
        return _cupertino(const AiTasteTrainingTutorialScreen());
      case RouteNames.slotMachineTutorial:
        return _cupertino(const SlotMachineTutorialScreen());
      case RouteNames.promiseAgreementTutorial:
        return _cupertino(const PromiseAgreementTutorialScreen());
      case RouteNames.seasonMeetingIntro:
        return _cupertino(const SeasonMeetingIntroScreen());
      case RouteNames.bambooForestIntroTutorial:
        return _cupertino(const BambooForestIntroTutorialScreen());
      case RouteNames.bambooForestSafetyTutorial:
        return _cupertino(const BambooForestSafetyTutorialScreen());
      case RouteNames.bambooForestWriteTutorial:
        return _cupertino(const BambooForestWriteTutorialScreen());

      // Main
      case RouteNames.main:
        final args = settings.arguments as MainScaffoldArgs?;
        return _cupertino(
          _adultGuard(
            MainScaffold(
              initialTabIndex: args?.initialTabIndex ?? 0,
              pendingRouteName: args?.pendingRouteName,
              pendingRouteArgs: args?.pendingRouteArgs,
            ),
          ),
        );

      // Matching
      case RouteNames.mysteryCard:
        return _cupertino(_adultGuard(const MysteryCardScreen()));
      case RouteNames.profileDiscovery:
        return _cupertino(_adultGuard(const ProfileDiscoveryScreen()));
      case RouteNames.profileCard:
        return _cupertino(_adultGuard(const ProfileCardScreen()));
      case RouteNames.aiPreference:
        return _cupertino(_adultGuard(const AiPreferenceScreen()));
      case RouteNames.aiMatchCard:
        return _cupertino(_adultGuard(const AiMatchCardScreen()));
      case RouteNames.profileSpecificDetail:
        final args = settings.arguments as ProfileCardArgs?;
        return _cupertino(
          _adultGuard(
            SensitiveScreenProtection(child: AiMatchProfileScreen(args: args)),
          ),
        );
      // Chat
      case RouteNames.premiumChatList:
        return _cupertino(
          _adultGuard(const SensitiveScreenProtection(child: ChatListScreen())),
        );
      case RouteNames.chatRoom:
        final data = settings.arguments as ChatRoomData?;
        return _cupertino(
          _adultGuard(
            ChatRoomScreen(
              chatRoomId: data?.chatRoomId ?? '',
              partnerId: data?.partnerId ?? '',
              partnerName: data?.partnerName ?? 'Kim Min-jun',
              partnerUniversity: data?.partnerUniversity ?? "Seoul Nat'l Univ",
              partnerAvatarUrl: data?.partnerAvatarUrl,
            ),
          ),
        );
      case RouteNames.groupChat:
      case RouteNames.groupMatch:
        return _cupertino(_adultGuard(const GroupMatchScreen()));
      case RouteNames.safetyStampFollowUp:
        final args = settings.arguments as SafetyStampFollowUpArgs?;
        return _cupertino(
          _adultGuard(
            SafetyStampFollowUpScreen(
              args:
                  args ??
                  const SafetyStampFollowUpArgs(roomId: '', promiseId: ''),
            ),
          ),
        );

      // Community

      case RouteNames.community:
        return _cupertino(_adultGuard(const CommunityScreen()));
      case RouteNames.postDetail:
        final postId = settings.arguments as String?;
        return _cupertino(_adultGuard(PostDetailScreen(postId: postId ?? '')));
      case RouteNames.postWrite:
        return _cupertino(_adultGuard(const PostWriteScreen()));

      // Profile
      case RouteNames.myPage:
      case RouteNames.profile:
        return _cupertino(_adultGuard(const MyPageScreen()));
      case RouteNames.heartCharge:
        return _cupertino(_adultGuard(const HeartChargeScreen()));
      case RouteNames.friendsList:
        return _cupertino(_adultGuard(const FriendsListScreen()));
      case RouteNames.profileEdit:
        return _cupertino(_adultGuard(const ProfileEditScreen()));
      case RouteNames.receivedHearts:
        return _cupertino(_adultGuard(const ReceivedHeartsScreen()));
      case RouteNames.sentHearts:
        return _cupertino(_adultGuard(const SentHeartsScreen()));
      case RouteNames.settings:
        return _cupertino(const SettingsScreen());
      case RouteNames.accountManagement:
        return _cupertino(const AccountManagementScreen());
      case RouteNames.notificationSettings:
        return _cupertino(const NotificationSettingsScreen());
      case RouteNames.safetyStampLogs:
        return _cupertino(const SafetyStampLogScreen());
      case RouteNames.contactBlock:
        return _cupertino(const ContactBlockScreen());
      case RouteNames.kakaoFriendMessageTest:
        return _cupertino(
          _showKakaoReviewTools
              ? const KakaoFriendMessageTestScreen()
              : const SizedBox.shrink(),
        );
      case RouteNames.asksInbox:
        return _cupertino(const AsksInboxScreen());
      case RouteNames.termsWebview:
        return _cupertino(const TermsWebViewScreen());
      case RouteNames.faq:
        return _cupertino(const FaqScreen());

      // Notifications
      case RouteNames.notifications:
        return _cupertino(_adultGuard(const NotificationListScreen()));

      // Reports
      case RouteNames.issueReport:
        return _cupertino(
          IssueReportScreen(
            onSubmit:
                ({
                  required String category,
                  required String content,
                  required bool allowContact,
                }) async {
                  try {
                    await IssueReportService().submitIssueReport(
                      category: category,
                      content: content,
                      allowContact: allowContact,
                    );
                    return true;
                  } catch (e) {
                    debugPrint('Issue report submit error: $e');
                    return false;
                  }
                },
          ),
        );
      case RouteNames.inquiry:
        return _cupertino(
          InquiryScreen(
            onSubmit:
                ({
                  required String category,
                  required String content,
                  required bool allowContact,
                }) async {
                  try {
                    await InquiryService().submitInquiry(
                      category: category,
                      content: content,
                      allowContact: allowContact,
                    );
                    return true;
                  } catch (e) {
                    debugPrint('Inquiry submit error: $e');
                    return false;
                  }
                },
          ),
        );

      // Event
      case RouteNames.event:
        return _cupertino(_adultGuard(const EventScreen()));
      case RouteNames.teamSetup:
        return _cupertino(_adultGuard(const TeamSetupScreen()));
      case RouteNames.eventAddFriend:
        return _cupertino(_adultGuard(const AddFriendScreen()));
      case RouteNames.eventTeamFriendPicker:
        final args = settings.arguments as TeamFriendPickerArgs?;
        if (args == null) {
          return _cupertino(
            const Scaffold(body: Center(child: Text('Missing arguments'))),
          );
        }
        return _cupertino(_adultGuard(TeamFriendPickerScreen(args: args)));
      case RouteNames.eventTeamInviteResponse:
        final args = settings.arguments as EventTeamInviteResponseArgs?;
        if (args == null) {
          return _cupertino(
            const Scaffold(body: Center(child: Text('Missing arguments'))),
          );
        }
        return _cupertino(
          _adultGuard(EventTeamInviteResponseScreen(args: args)),
        );
      case RouteNames.seasonMeetingRoulette:
        final args = settings.arguments as SeasonMeetingRouletteArgs?;
        return _cupertino(_adultGuard(SeasonMeetingRouletteScreen(args: args)));
      case RouteNames.matchResult:
        final args = settings.arguments as EventMatchResultArgs?;
        return _cupertino(_adultGuard(MatchResultScreen(args: args)));
      case RouteNames.randomMatching:
        return _cupertino(_adultGuard(const RandomMatchingScreen()));
      case RouteNames.randomMathcingWait:
        return _cupertino(
          _adultGuard(const SlotMachineScreen()),
        ); // random_mathcing_screen.dart
      case RouteNames.randomMeeting:
        return _cupertino(_adultGuard(const RandomMeetingScreen()));
      case RouteNames.threeVsThreeMatch:
        final args = settings.arguments as ThreeVsThreeMatchArgs?;
        return _cupertino(_adultGuard(ThreeVsThreeMatchScreen(args: args)));
      case RouteNames.teamRequests:
        return _cupertino(_adultGuard(const TeamRequestsScreen()));
      case RouteNames.teamRequestDeclined:
        final args = settings.arguments as TeamRequestDeclinedArgs?;
        return _cupertino(_adultGuard(TeamRequestDeclinedScreen(args: args)));

      // Meeting
      case RouteNames.meetingApplication:
        return _cupertino(_adultGuard(const MeetingApplicationScreen()));

      default:
        return _cupertino(
          Scaffold(
            body: Center(child: Text('Route not found: ${settings.name}')),
          ),
        );
    }
  }

  static CupertinoPageRoute<T> _cupertino<T>(Widget page) {
    return CupertinoPageRoute<T>(builder: (_) => page);
  }

  static Widget _adultGuard(Widget child) {
    return _AdultVerifiedRouteGuard(child: child);
  }
}

class _AdultVerifiedRouteGuard extends StatefulWidget {
  const _AdultVerifiedRouteGuard({required this.child});

  final Widget child;

  @override
  State<_AdultVerifiedRouteGuard> createState() =>
      _AdultVerifiedRouteGuardState();
}

class _AdultVerifiedRouteGuardState extends State<_AdultVerifiedRouteGuard> {
  late final Future<bool> _adultVerified = _checkAdultVerified();

  Future<bool> _checkAdultVerified() async {
    final kakaoUserId = await StorageService().getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) return false;
    return AuthService().isAdultVerified(kakaoUserId);
  }

  void _redirectToAdultVerification() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(RouteNames.adultVerification, (route) => false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _adultVerified,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const CupertinoPageScaffold(
            backgroundColor: Color(0xFFFAFAFA),
            child: Center(
              child: CupertinoActivityIndicator(color: Color(0xFFFF6B8A)),
            ),
          );
        }

        if (snapshot.data == true) {
          return widget.child;
        }

        _redirectToAdultVerification();
        return const CupertinoPageScaffold(
          backgroundColor: Color(0xFFFAFAFA),
          child: Center(
            child: Text(
              '본인인증 완료 후 이용할 수 있어요.',
              style: TextStyle(
                fontFamily: 'NanumSquareRound',
                fontSize: 15,
                color: Color(0xFF64748B),
              ),
            ),
          ),
        );
      },
    );
  }
}
