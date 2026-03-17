import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'route_names.dart';

// Splash & Auth (로그인 화면 없음: /login → 카카오 인증 화면으로 통일)
import '../features/splash/splash_screen.dart';
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
import '../services/ai_recommendation_service.dart';

// Chat
import '../features/chat/screens/premium_chat_list_screen.dart';
import '../features/chat/screens/chat_room_screen.dart';
import '../features/chat/screens/group_match_screen.dart';
import '../features/chat/models/chat_room_data.dart';

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
import '../features/profile/screens/settings_screen.dart';
import '../features/matching/models/profile_card_args.dart';
import '../features/profile/screens/terms_webview_screen.dart';

// Notifications
import '../features/notifications/screens/notification_list_screen.dart';

// Event
import '../features/event/screens/event_screen.dart';
import '../features/event/screens/team_setup_screen.dart';
import '../features/event/screens/season_meeting_roulette_screen.dart';
import '../features/event/screens/match_result_screen.dart';
import '../features/event/screens/random_matching_screen1.dart';
import '../features/event/screens/random_mathcing_screen.dart';
import '../features/event/screens/random_meeting_screen.dart';
import '../features/event/screens/three_vs_three_match_screen.dart';

// Meeting
import '../features/meeting/screens/meeting_application_screen.dart';

import '../shared/layouts/main_scaffold_args.dart';

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
        return _cupertino(const DepartmentScreen());
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
        );

      // Matching
      case RouteNames.mysteryCard:
        return _cupertino(const MysteryCardScreen());
      case RouteNames.profileDiscovery:
        return _cupertino(const ProfileDiscoveryScreen());
      case RouteNames.profileCard:
        return _cupertino(const ProfileCardScreen());
      case RouteNames.aiPreference:
        return _cupertino(const AiPreferenceScreen());
      case RouteNames.aiMatchCard:
        return _cupertino(const AiMatchCardScreen());
      case RouteNames.profileSpecificDetail:
        final args = settings.arguments as ProfileCardArgs?;
        return _cupertino(AiMatchProfileScreen(args: args));
      // Chat
      case RouteNames.premiumChatList:
        return _cupertino(const ChatListScreen());
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
      case RouteNames.groupChat:
      case RouteNames.groupMatch:
        return _cupertino(const GroupMatchScreen());

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
      case RouteNames.termsWebview:
        return _cupertino(const TermsWebViewScreen());

      // Notifications
      case RouteNames.notifications:
        return _cupertino(const NotificationListScreen());

      // Event
      case RouteNames.event:
        return _cupertino(const EventScreen());
      case RouteNames.teamSetup:
        return _cupertino(const TeamSetupScreen());
      case RouteNames.seasonMeetingRoulette:
        return _cupertino(const SeasonMeetingRouletteScreen());
      case RouteNames.matchResult:
        return _cupertino(const MatchResultScreen());
      case RouteNames.randomMatching:
        return _cupertino(const RandomMatchingScreen());
      case RouteNames.randomMathcingWait:
        return _cupertino(
          const SlotMachineScreen(),
        ); // random_mathcing_screen.dart
      case RouteNames.randomMeeting:
        return _cupertino(const RandomMeetingScreen());
      case RouteNames.threeVsThreeMatch:
        return _cupertino(const ThreeVsThreeMatchScreen());

      // Meeting
      case RouteNames.meetingApplication:
        return _cupertino(const MeetingApplicationScreen());

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
}
