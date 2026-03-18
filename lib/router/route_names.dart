/// 라우트 이름 상수 (흐름도 단일 소스)
class RouteNames {
  RouteNames._();

  // Auth
  static const String splash = '/';
  static const String login = '/login';
  static const String kakaoAuth = '/kakao-auth';
  static const String terms = '/terms';
  static const String studentVerification = '/student-verification';

  // Onboarding
  static const String onboardingBasicInfo = '/onboarding/basic-info';
  static const String onboardingInterestsSelection =
      '/onboarding/interests-selection';
  static const String onboardingLifestyle = '/onboarding/lifestyle';
  static const String onboardingMajor = '/onboarding/major';
  static const String onboardingDepartment = '/onboarding/department';
  static const String onboardingPhoto = '/onboarding/photo';
  static const String onboardingSelfIntro = '/onboarding/self-intro';
  static const String onboardingProfileQa = '/onboarding/profile-qa';
  static const String onboardingKeywords = '/onboarding/keywords';
  static const String onboardingIdealType = '/onboarding/ideal-type';
  static const String onboardingHeightSelection =
      '/onboarding/height-selection';
  static const String onboardingIdealHeightRange =
      '/onboarding/ideal-height-range';
  static const String onboardingIdealAge = '/onboarding/ideal/age';
  static const String onboardingIdealHeight = '/onboarding/ideal/height';
  static const String onboardingIdealMbti = '/onboarding/ideal/mbti';
  static const String onboardingIdealDepartment =
      '/onboarding/ideal/department';
  static const String onboardingIdealPersonality =
      '/onboarding/ideal/personality';
  static const String onboardingIdealLifestyle = '/onboarding/ideal/lifestyle';
  static const String onboardingInterests = '/onboarding/interests';

  // Tutorial
  static const String tutorial = '/tutorial';
  static const String welcomeTutorial = '/tutorial/welcome';
  static const String todaysMatchTutorial = '/tutorial/todays-match';
  static const String aiTasteButtonTutorial = '/tutorial/ai-taste-button';
  static const String aiTasteTraining = '/tutorial/ai-taste-training';
  static const String aiTasteTrainingTutorial =
      '/tutorial/ai-taste-training-tutorial';
  static const String slotMachineTutorial = '/tutorial/slot-machine';
  static const String promiseAgreementTutorial = '/tutorial/promise-agreement';
  static const String seasonMeetingIntro = '/tutorial/season-meeting-intro';
  static const String bambooForestIntroTutorial =
      '/tutorial/bamboo-forest-intro';
  static const String bambooForestSafetyTutorial =
      '/tutorial/bamboo-forest-safety';
  static const String bambooForestWriteTutorial =
      '/tutorial/bamboo-forest-write';

  // Main (탭 루트)
  static const String main = '/main';
  static const String matching = '/matching';
  static const String community = '/community';
  static const String event = '/event';
  static const String chat = '/chat';
  static const String profile = '/profile';

  // Matching (1:1)
  static const String mysteryCard = '/matching/mystery-card';
  static const String profileDiscovery = '/matching/profile-discovery';
  static const String profileCard = '/matching/profile-card';
  static const String aiMatchCard = '/matching/ai-match-card';
  static const String profileSpecificDetail =
      '/matching/profile-specific-detail';
  static const String profileDetail = '/matching/profile-detail';
  static const String profileExpanded = '/matching/profile-expanded';
  static const String aiPreference = '/matching/ai-preference';

  // Chat
  static const String premiumChatList = '/chat/list';
  static const String chatRoom = '/chat/room';
  static const String groupChat = '/chat/group';

  // Community (대나무숲)
  static const String postDetail = '/community/post';
  static const String postWrite = '/community/write';

  // Profile (내 페이지)
  static const String myPage = '/profile/my-page';
  static const String heartCharge = '/profile/charge';
  static const String friendsList = '/profile/friends';
  static const String profileEdit = '/profile/edit';
  static const String receivedHearts = '/profile/hearts';
  static const String sentHearts = '/profile/sent-hearts';
  static const String settings = '/profile/settings';
  static const String termsWebview = '/profile/terms-webview';
  static const String inquiry = '/profile/inquiry';

  static const String notifications = '/notifications';
  static const String issueReport = '/profile/issue-report';

  // Event
  static const String teamSetup = '/event/team-setup';
  static const String seasonMeetingRoulette = '/event/season-meeting-roulette';
  static const String matchResult = '/event/match-result';
  static const String randomMatching = '/event/random-matching';
  static const String randomMathcingWait =
      '/event/random-matching-wait'; // 신청 내역 (typo 유지)
  static const String randomMeeting = '/event/random-meeting';
  static const String threeVsThreeMatch = '/event/three-vs-three-match';
  static const String groupMatch = '/event/3v3';
  static const String groupLobby = '/event/3v3/lobby';
  static const String slotMachine = '/event/slot-machine';
  static const String groupProfile = '/event/group-profile';
  static const String partnership = '/event/partnership';

  // Meeting
  static const String meetingApplication = '/meeting/application';
}
