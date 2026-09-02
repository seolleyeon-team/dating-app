import 'package:seolleyeon/shared/utils/privacy_log_utils.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'route_names.dart';

// Splash & Auth (/login = 연세 이메일 primary 로그인, /kakao-auth 는 legacy alias)
import '../features/splash/splash_screen.dart';
import '../features/auth/screens/adult_verification_gate_screen.dart';
import '../features/auth/screens/kakao_friend_connection_screen.dart';
import '../features/auth/screens/student_verification_screen.dart';
import '../features/onboarding/screens/terms_screen.dart';

// Onboarding
import '../features/onboarding/screens/basic_info_screen.dart';
import '../features/onboarding/screens/interests_screen.dart';
import '../features/onboarding/screens/interests_selection_screen.dart';
import '../features/onboarding/onboarding_route_args.dart';
import '../features/onboarding/screens/lifestyle_screen.dart';
import '../features/onboarding/screens/major_selection_screen.dart';
import '../features/onboarding/screens/department_screen.dart';
import '../features/onboarding/screens/campus_life_zone_repair_screen.dart';
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
import '../features/matching/screens/ai_preference_screen.dart';
import '../features/matching/screens/ai_match_card_screen.dart';
import '../features/matching/screens/profile_specific_detail_screen.dart';
import '../shared/widgets/sensitive_screen_protection.dart';

// Chat
import '../features/chat/screens/premium_chat_list_screen.dart';
import '../features/chat/screens/chat_room_screen.dart';
import '../features/chat/screens/support_user_directory_screen.dart';
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
import '../features/profile/screens/safety_stamp_log_screen.dart';
import '../features/profile/screens/contact_block_screen.dart';
import '../features/profile/screens/kakao_friend_message_test_screen.dart';
import '../features/matching/models/profile_card_args.dart';
import '../features/profile/screens/terms_webview_screen.dart';
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
import '../features/event/screens/season_meeting_payment_guide_screen.dart';
import '../features/event/meeting_icebreaker/presentation/bomb_pass_timer_screen.dart';
import '../features/event/screens/match_result_screen.dart';
import '../features/event/screens/random_mathcing_screen.dart';
import '../features/event/screens/three_vs_three_match_screen.dart';
import '../features/event/screens/team_requests_screen.dart';
import '../features/event/screens/team_request_declined_screen.dart';

// Blind taste meeting (3:3 블라인드 취향 미팅)
import '../features/blind_meeting/data/blind_meeting_profile_snapshot.dart';
import '../features/blind_meeting/presentation/blind_meeting_route_args.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_dna_wizard_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_feedback_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_follow_up_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_intro_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_party_friend_picker_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_party_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_result_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_schedule_screen.dart';
import '../features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart';

import '../shared/layouts/main_scaffold_args.dart';

/// 앱 라우터 (CupertinoPageRoute, 흐름도 단일 소스)
class AppRouter {
  static Route<dynamic> generateRoute(RouteSettings settings) {
    final name = settings.name ?? '';

    switch (name) {
      // Auth
      case RouteNames.splash:
        return _cupertino(const SplashScreen());
      // PRIMARY 로그인 = 연세 이메일. legacy /kakao-auth 링크도 같은 화면으로
      // 안전하게 흡수한다 (카카오 로그인 화면은 존재하지 않는다).
      case RouteNames.login:
      case RouteNames.kakaoAuth:
      case RouteNames.studentVerification:
        return _cupertino(const StudentVerificationScreen());
      case RouteNames.adultVerification:
        return _cupertino(const AdultVerificationGateScreen());
      case RouteNames.terms:
        return _cupertino(const TermsScreen());
      // Post-auth 카카오 친구 연결 (아는 사람 추천 차단 전용, 인증 아님)
      case RouteNames.kakaoFriendConnect:
        return _cupertino(const KakaoFriendConnectionScreen());

      // Onboarding
      case RouteNames.onboardingBasicInfo:
        return _cupertino(const BasicInfoScreen());
      case RouteNames.onboardingInterestsSelection:
        {
          final args = settings.arguments;
          final mode = args is InterestsSelectionRouteArgs
              ? args.mode
              : InterestsSelectionMode.onboarding;
          return _cupertino(InterestsSelectionScreen(mode: mode));
        }
      case RouteNames.onboardingLifestyle:
        return _cupertino(const LifestyleScreen());
      case RouteNames.onboardingMajor:
        return _cupertino(const MajorSelectionScreen());
      case RouteNames.onboardingDepartment:
        return _cupertino(const DepartmentScreen());
      case RouteNames.campusLifeZoneRepair:
        return _cupertino(const CampusLifeZoneRepairScreen());
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
          MainScaffold(
            initialTabIndex: args?.initialTabIndex ?? 0,
            pendingRouteName: args?.pendingRouteName,
            pendingRouteArgs: args?.pendingRouteArgs,
          ),
          settings: settings,
        );

      // Matching
      case RouteNames.mysteryCard:
        return _cupertino(const MysteryCardScreen());
      case RouteNames.profileDiscovery:
        return _cupertino(const ProfileDiscoveryScreen());
      case RouteNames.aiPreference:
        return _cupertino(const AiPreferenceScreen());
      case RouteNames.aiMatchCard:
        return _cupertino(const AiMatchCardScreen());
      case RouteNames.profileSpecificDetail:
        final args = settings.arguments as ProfileCardArgs?;
        return _cupertino(
          SensitiveScreenProtection(child: AiMatchProfileScreen(args: args)),
        );
      // Chat
      case RouteNames.premiumChatList:
        return _cupertino(
          const SensitiveScreenProtection(child: ChatListScreen()),
        );
      case RouteNames.chatRoom:
        final data = settings.arguments as ChatRoomData?;
        return _cupertino(
          ChatRoomScreen(
            chatRoomId: data?.chatRoomId ?? '',
            partnerId: data?.partnerId ?? '',
            partnerName: data?.partnerName ?? 'Kim Min-jun',
            partnerUniversity: data?.partnerUniversity ?? "Seoul Nat'l Univ",
            partnerAvatarUrl: data?.partnerAvatarUrl,
          ),
        );
      case RouteNames.supportUserDirectory:
        return _cupertino(const SupportUserDirectoryScreen());
      case RouteNames.groupChat:
      case RouteNames.groupMatch:
        return _cupertino(const GroupMatchScreen());
      case RouteNames.safetyStampFollowUp:
        final args = settings.arguments as SafetyStampFollowUpArgs?;
        return _cupertino(
          SafetyStampFollowUpScreen(
            args:
                args ??
                const SafetyStampFollowUpArgs(roomId: '', promiseId: ''),
          ),
        );

      // Community

      case RouteNames.community:
        return _cupertino(const CommunityScreen());
      case RouteNames.postDetail:
        final postId = settings.arguments as String?;
        return _cupertino(PostDetailScreen(postId: postId ?? ''));
      case RouteNames.postWrite:
        return _cupertino(const PostWriteScreen());

      // Profile
      case RouteNames.myPage:
      case RouteNames.profile:
        return _cupertino(const MyPageScreen());
      case RouteNames.heartCharge:
        return _cupertino(const HeartChargeScreen());
      case RouteNames.friendsList:
        return _cupertino(const FriendsListScreen());
      case RouteNames.profileEdit:
        return _cupertino(const ProfileEditScreen());
      case RouteNames.receivedHearts:
        return _cupertino(const ReceivedHeartsScreen());
      case RouteNames.sentHearts:
        return _cupertino(const SentHeartsScreen());
      case RouteNames.settings:
        return _cupertino(const SettingsScreen());
      case RouteNames.accountManagement:
        return _cupertino(const AccountManagementScreen());
      case RouteNames.safetyStampLogs:
        return _cupertino(const SafetyStampLogScreen());
      case RouteNames.contactBlock:
        return _cupertino(const ContactBlockScreen());
      case RouteNames.kakaoFriendMessageTest:
        return _cupertino(const KakaoFriendMessageTestScreen());
      case RouteNames.asksInbox:
        return _cupertino(const AsksInboxScreen());
      case RouteNames.termsWebview:
        return _cupertino(const TermsWebViewScreen());

      // Notifications
      case RouteNames.notifications:
        return _cupertino(const NotificationListScreen());

      // Reports
      case RouteNames.issueReport:
        return _cupertino(
          IssueReportScreen(
            onSubmit:
                ({
                  required String category,
                  required String content,
                  required bool allowOperationsFollowUp,
                }) async {
                  try {
                    return await IssueReportService().submitIssueReport(
                      category: category,
                      content: content,
                      allowOperationsFollowUp: allowOperationsFollowUp,
                    );
                  } catch (e) {
                    debugPrint(
                      'Issue report submit error: ${PrivacyLogUtils.errorSummary(e)}',
                    );
                    return null;
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
                  required bool allowOperationsFollowUp,
                }) async {
                  try {
                    return await InquiryService().submitInquiry(
                      category: category,
                      content: content,
                      allowOperationsFollowUp: allowOperationsFollowUp,
                    );
                  } catch (e) {
                    debugPrint(
                      'Inquiry submit error: ${PrivacyLogUtils.errorSummary(e)}',
                    );
                    return null;
                  }
                },
          ),
        );

      // Event
      case RouteNames.event:
        return _cupertino(const EventScreen(), settings: settings);
      case RouteNames.teamSetup:
        return _cupertino(const TeamSetupScreen());
      case RouteNames.eventAddFriend:
        return _cupertino(const AddFriendScreen());
      case RouteNames.eventTeamFriendPicker:
        final args = settings.arguments as TeamFriendPickerArgs?;
        if (args == null) {
          return _cupertino(
            const Scaffold(body: Center(child: Text('Missing arguments'))),
          );
        }
        return _cupertino(TeamFriendPickerScreen(args: args));
      case RouteNames.eventTeamInviteResponse:
        final args = settings.arguments as EventTeamInviteResponseArgs?;
        if (args == null) {
          return _cupertino(
            const Scaffold(body: Center(child: Text('Missing arguments'))),
          );
        }
        return _cupertino(EventTeamInviteResponseScreen(args: args));
      case RouteNames.seasonMeetingRoulette:
        final args = settings.arguments as SeasonMeetingRouletteArgs?;
        return _cupertino(SeasonMeetingRouletteScreen(args: args));
      case RouteNames.seasonMeetingPaymentGuide:
        return _cupertino(const SeasonMeetingPaymentGuideScreen());
      case RouteNames.matchResult:
        final args = settings.arguments as EventMatchResultArgs?;
        return _cupertino(MatchResultScreen(args: args));
      case RouteNames.randomMathcingWait:
        return _cupertino(
          const SlotMachineScreen(),
        ); // random_mathcing_screen.dart
      case RouteNames.threeVsThreeMatch:
        final args = settings.arguments as ThreeVsThreeMatchArgs?;
        return _cupertino(ThreeVsThreeMatchScreen(args: args));
      case RouteNames.teamRequests:
        return _cupertino(const TeamRequestsScreen());
      case RouteNames.teamRequestDeclined:
        final args = settings.arguments as TeamRequestDeclinedArgs?;
        return _cupertino(TeamRequestDeclinedScreen(args: args));

      // Blind taste meeting (3:3 블라인드 취향 미팅)
      //
      // legacy 랜덤 미팅 deep link는 그대로 살려두고 새 소개 화면으로 보낸다.
      case RouteNames.blindTasteMeetingParty:
        return _cupertino(const BlindMeetingPartyScreen(), settings: settings);
      case RouteNames.blindTasteMeetingPartyFriendPicker:
        final partyId = settings.arguments;
        if (partyId is! String || partyId.trim().isEmpty) {
          return _cupertino(
            const BlindMeetingPartyScreen(),
            settings: const RouteSettings(
              name: RouteNames.blindTasteMeetingParty,
            ),
          );
        }
        return _cupertino(
          BlindMeetingPartyFriendPickerScreen(partyId: partyId),
          settings: settings,
        );
      case RouteNames.blindTasteMeeting:
      case RouteNames.legacyRandomMatching:
      case RouteNames.legacyRandomMeeting:
      case RouteNames.legacyMeetingApplication:
        return _cupertino(
          const BlindMeetingIntroScreen(enablePaidDnaStart: true),
          settings: settings,
        );
      case RouteNames.blindTasteMeetingDna:
        {
          final rawArgs = settings.arguments;
          final profile = rawArgs is BlindMeetingDnaRouteArgs
              ? rawArgs.profile
              : rawArgs is BlindMeetingProfileSnapshot
              ? rawArgs
              : null;
          final mode = rawArgs is BlindMeetingDnaRouteArgs
              ? rawArgs.mode
              : BlindMeetingDnaMode.create;
          final heartCharged = rawArgs is BlindMeetingDnaRouteArgs
              ? rawArgs.heartCharged
              : false;
          final persistProgress = rawArgs is BlindMeetingDnaRouteArgs
              ? rawArgs.persistProgress
              : false;
          if (profile is! BlindMeetingProfileSnapshot) {
            return _cupertino(
              const BlindMeetingIntroScreen(enablePaidDnaStart: true),
              settings: RouteSettings(name: RouteNames.blindTasteMeeting),
            );
          }
          return _cupertino(
            BlindMeetingDnaWizardScreen(
              profile: profile,
              mode: mode,
              heartCharged: heartCharged,
              persistProgress: persistProgress,
            ),
            settings: settings,
          );
        }
      case RouteNames.blindTasteMeetingSchedule:
        {
          final draft = settings.arguments;
          if (draft is! BlindMeetingDnaDraft) {
            return _cupertino(
              const BlindMeetingIntroScreen(enablePaidDnaStart: true),
              settings: RouteSettings(name: RouteNames.blindTasteMeeting),
            );
          }
          return _cupertino(
            BlindMeetingScheduleScreen(draft: draft),
            settings: settings,
          );
        }
      case RouteNames.blindTasteMeetingWaiting:
        return _cupertino(
          const BlindMeetingWaitingScreen(),
          settings: settings,
        );
      case RouteNames.blindTasteMeetingResult:
        {
          final args = settings.arguments;
          if (args is! BlindMeetingMeetingArgs) {
            return _cupertino(
              const BlindMeetingIntroScreen(enablePaidDnaStart: true),
            );
          }
          return _cupertino(BlindMeetingResultScreen(args: args));
        }
      case RouteNames.blindTasteMeetingFollowUp:
        {
          final args = settings.arguments;
          if (args is! BlindMeetingMeetingArgs) {
            return _cupertino(
              const BlindMeetingIntroScreen(enablePaidDnaStart: true),
            );
          }
          return _cupertino(BlindMeetingFollowUpScreen(args: args));
        }
      case RouteNames.blindTasteMeetingFeedback:
        {
          final args = settings.arguments;
          if (args is! BlindMeetingMeetingArgs) {
            return _cupertino(
              const BlindMeetingIntroScreen(enablePaidDnaStart: true),
            );
          }
          return _cupertino(BlindMeetingFeedbackScreen(args: args));
        }

      // 3:3 미팅 아이스브레이킹 — 폭탄 돌리기 타이머
      case RouteNames.meetingIcebreakerBombTimer:
        {
          final args = settings.arguments;
          return _cupertino(
            BombPassTimerScreen(args: args is BombPassTimerArgs ? args : null),
          );
        }

      default:
        return _cupertino(
          Scaffold(
            body: Center(child: Text('Route not found: ${settings.name}')),
          ),
        );
    }
  }

  static CupertinoPageRoute<T> _cupertino<T>(
    Widget page, {
    RouteSettings? settings,
  }) {
    return CupertinoPageRoute<T>(builder: (_) => page, settings: settings);
  }
}
