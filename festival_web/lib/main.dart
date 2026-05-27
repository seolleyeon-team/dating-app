// ignore_for_file: sort_child_properties_last

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:firebase_storage/firebase_storage.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:image_picker/image_picker.dart';

import 'package:cloud_functions/cloud_functions.dart';

import 'festival_push_service.dart';
import 'firebase_options.dart';
import 'mobile_web_keyboard.dart';
import 'festival_event_schedule.dart';
import 'avatar/avatar_candidate_dialog.dart';
import 'avatar/avatar_display_resolver.dart';
import 'avatar/avatar_generating_overlay.dart';
import 'avatar/avatar_generation_client.dart';
import 'avatar/avatar_generation_models.dart';
import 'avatar/avatar_photo_input.dart';
import 'recommendation/festival_recommendation_engine.dart';
import 'recommendation/festival_taste_affinity.dart';

final GlobalKey<NavigatorState> festivalRootNavigatorKey =
    GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  usePathUrlStrategy();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  FestivalPushAuthBridge.hasActiveSession = () =>
      FestivalBackend.instance.isAuthenticated;
  FestivalPushNavigationBridge.openChatRoom = _openChatFromPush;
  await FestivalPushService.instance.initializeSafely();
  await FestivalBackend.instance.configureAuthPersistence();
  await FestivalBackend.instance.restoreSession();
  if (FestivalBackend.instance.isAuthenticated) {
    await FestivalPushService.instance.syncTokenSafely();
  }
  runApp(const FestivalWebApp());
}

Future<void> _openChatFromPush(String roomId) async {
  final profile = await FestivalBackend.instance.profileForChatRoom(roomId);
  final navigator = festivalRootNavigatorKey.currentState;
  if (profile == null || navigator == null) return;
  navigator.pushNamed(AppRoutes.chat, arguments: profile);
}

class FestivalWebApp extends StatefulWidget {
  const FestivalWebApp({super.key});

  @override
  State<FestivalWebApp> createState() => _FestivalWebAppState();
}

class _FestivalWebAppState extends State<FestivalWebApp> {
  late final ValueNotifier<double> _mobileWebKeyboardInset;

  @override
  void initState() {
    super.initState();
    _mobileWebKeyboardInset = createMobileWebKeyboardInsetNotifier();
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<double>(
      valueListenable: _mobileWebKeyboardInset,
      builder: (context, mobileWebInset, _) {
        return MaterialApp(
          navigatorKey: festivalRootNavigatorKey,
          title: '설레연 페스티벌',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            useMaterial3: true,
            fontFamily: AppFonts.body,
            brightness: Brightness.light,
            scaffoldBackgroundColor: AppColors.background,
            colorScheme: const ColorScheme.light(
              primary: AppColors.primary,
              secondary: AppColors.mint,
              surface: AppColors.surface,
              onPrimary: Colors.white,
              onSurface: AppColors.textMain,
            ),
            textTheme: ThemeData.light().textTheme.apply(
              fontFamily: AppFonts.body,
              bodyColor: AppColors.textMain,
              displayColor: AppColors.textMain,
            ),
          ),
          builder: (context, child) {
            if (child == null) return const SizedBox.shrink();
            final mediaQuery = MediaQuery.of(context);
            final mergedBottom = kIsWeb
                ? math.max(mediaQuery.viewInsets.bottom, mobileWebInset)
                : mediaQuery.viewInsets.bottom;
            if (mergedBottom == mediaQuery.viewInsets.bottom) {
              return child;
            }
            return MediaQuery(
              data: mediaQuery.copyWith(
                viewInsets: mediaQuery.viewInsets.copyWith(
                  bottom: mergedBottom,
                ),
              ),
              child: child,
            );
          },
          onGenerateRoute: _route,
        );
      },
    );
  }

  Route<void> _route(RouteSettings settings) {
    final uri = Uri.parse(settings.name ?? AppRoutes.access);
    final path = uri.path.isEmpty ? AppRoutes.access : uri.path;
    final segments = uri.pathSegments;
    Widget screen;

    if (segments.length == 2 && segments.first == 'r') {
      screen = RedeemScreen(token: Uri.decodeComponent(segments.last));
      return MaterialPageRoute<void>(
        settings: settings,
        builder: (_) => screen,
      );
    }

    switch (path) {
      case AppRoutes.start:
        screen = const AuthGate(child: OnboardingRedirectScreen());
      case AppRoutes.signup:
        screen = const AuthGate(child: SignupScreen());
      case AppRoutes.taste:
        screen = AuthGate(
          child: TasteTrainingScreen(
            resume: settings.arguments is TasteTrainingResume
                ? settings.arguments! as TasteTrainingResume
                : null,
          ),
        );
      case AppRoutes.waiting:
        screen = const AuthGate(child: WaitingScreen());
      case AppRoutes.matches:
        screen = const AuthGate(child: TodayMatchScreen());
      case AppRoutes.profile:
        screen = AuthGate(
          child: ProfileDetailScreen(
            profile: settings.arguments is FestivalProfile
                ? settings.arguments! as FestivalProfile
                : sampleProfiles.first,
          ),
        );
      case AppRoutes.chat:
        screen = AuthGate(
          child: ChatScreen(
            profile: settings.arguments is FestivalProfile
                ? settings.arguments! as FestivalProfile
                : sampleProfiles.first,
          ),
        );
      case AppRoutes.fontMockup:
        screen = const FontMockupScreen();
      case AppRoutes.access:
      default:
        screen = const FestivalEntryScreen();
    }

    return MaterialPageRoute<void>(settings: settings, builder: (_) => screen);
  }
}

class AppRoutes {
  static const access = '/';
  static const start = '/start';
  static const signup = '/signup';
  static const taste = '/taste';
  static const waiting = '/waiting';
  static const matches = '/matches';
  static const profile = '/profile';
  static const chat = '/chat';
  static const fontMockup = '/font-mockup';
}

class AppFonts {
  static const body = 'GriunGyuwon';
  static const meongi = 'FestivalMeongiOutlineThick';
}

class AppColors {
  static const primary = Color(0xFFE48CB1);
  static const primaryDeep = Color(0xFFB8587A);
  static const blush = Color(0xFFFFF8FB);
  static const background = Color(0xFFFFF4F8);
  static const desktopBackground = Color(0xFFFFF4F8);
  static const surface = Color(0xFFFFFFFE);
  static const input = Color(0xFFFFF8FB);
  static const border = Color(0xFFF0DCE5);
  static const textMain = Color(0xFF4A313B);
  static const textSub = Color(0xFF9A7785);
  static const textHint = Color(0xFFC6A8B4);
  static const mint = Color(0xFF8ECFC4);
  static const blue = Color(0xFF8EB6E8);
  static const amber = Color(0xFFE9BD77);
  static const purple = Color(0xFFB9A2E5);
}

const Duration _ticketSessionDuration = Duration(hours: 48);

const double _kMaxPageWidth = 480;
const int _tasteCardCount = 20;
const String _profileCardImageAsset = 'assets/images/aiprofile_card.jpg';

void _runSilently(Future<void> future) {
  unawaited(future.catchError((Object _) {}));
}

String _normalizeTicketCode(String rawCode) {
  return rawCode.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]'), '');
}

DateTime? _readDate(Object? value) {
  if (value is Timestamp) return value.toDate();
  if (value is DateTime) return value;
  if (value is String) return DateTime.tryParse(value);
  return null;
}

String _formatChatTime(Object? value) {
  final date = _readDate(value);
  if (date == null) return '';
  final now = DateTime.now();
  final local = date.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  if (now.year == local.year &&
      now.month == local.month &&
      now.day == local.day) {
    return '$hour:$minute';
  }
  return '${local.month}/${local.day}';
}

class FestivalSession {
  final String uid;
  final String ticketId;
  final String code;
  final DateTime sessionExpiresAt;

  const FestivalSession({
    required this.uid,
    required this.ticketId,
    required this.code,
    required this.sessionExpiresAt,
  });

  factory FestivalSession.fromMap(Map<String, dynamic> data) {
    return FestivalSession(
      uid: data['uid'] as String? ?? '',
      ticketId: data['ticketId'] as String? ?? '',
      code: data['code'] as String? ?? '',
      sessionExpiresAt:
          _readDate(data['sessionExpiresAt']) ??
          DateTime.fromMillisecondsSinceEpoch(0),
    );
  }

  bool get isActive {
    return uid.isNotEmpty &&
        ticketId.isNotEmpty &&
        sessionExpiresAt.isAfter(DateTime.now());
  }
}

class FestivalBackendException implements Exception {
  final String message;

  const FestivalBackendException(this.message);

  @override
  String toString() => message;
}

String _avatarContentTypeForFileName(String fileName, String? mimeType) {
  final normalized = (mimeType ?? '').trim().toLowerCase();
  if (normalized == 'image/jpeg' ||
      normalized == 'image/png' ||
      normalized == 'image/webp') {
    return normalized;
  }
  final lower = fileName.toLowerCase().trim();
  if (lower.endsWith('.png')) return 'image/png';
  if (lower.endsWith('.webp')) return 'image/webp';
  return 'image/jpeg';
}

class ProfileDraft {
  final String nickname;
  final String gender;
  final String department;
  final String? studentAffiliation;
  final int age;
  final String mbti;
  final String intro;
  final bool hasPhoto;
  final String? photoUrl;
  final String? photoStoragePath;
  final String? photoContentType;
  final String? photoOriginalName;
  final int? photoSizeBytes;

  const ProfileDraft({
    required this.nickname,
    required this.gender,
    required this.department,
    required this.studentAffiliation,
    required this.age,
    required this.mbti,
    required this.intro,
    required this.hasPhoto,
    this.photoUrl,
    this.photoStoragePath,
    this.photoContentType,
    this.photoOriginalName,
    this.photoSizeBytes,
  });

  factory ProfileDraft.fromMap(Map<String, dynamic> data) {
    final mbti = data['mbti'] as String? ?? 'ENFP';
    final avatarUrl = FestivalAvatarDisplayResolver.resolve(data);
    return ProfileDraft(
      nickname: data['nickname'] as String? ?? '',
      gender: data['gender'] as String? ?? '',
      department: data['department'] as String? ?? '',
      studentAffiliation: data['studentAffiliation'] as String?,
      age: data['age'] is int ? data['age'] as int : 22,
      mbti: mbti.length == 4 ? mbti : 'ENFP',
      intro: data['intro'] as String? ?? '',
      hasPhoto: avatarUrl.isNotEmpty,
      photoUrl: avatarUrl.isEmpty ? null : avatarUrl,
      photoStoragePath: null,
      photoContentType: null,
      photoOriginalName: data['photoOriginalName'] as String?,
      photoSizeBytes: data['photoSizeBytes'] is int
          ? data['photoSizeBytes'] as int
          : null,
    );
  }
}

class FestivalBackend {
  FestivalBackend._();

  static final FestivalBackend instance = FestivalBackend._();

  final FirebaseAuth _auth = FirebaseAuth.instance;
  final FirebaseFirestore _db = FirebaseFirestore.instance;
  final FirebaseStorage _storage = FirebaseStorage.instance;
  final FestivalEventScheduleService _eventSchedule =
      FestivalEventScheduleService(FirebaseFirestore.instance);
  FestivalSession? _session;

  Stream<FestivalEventSchedule?> watchEventSchedule() => _eventSchedule.watch();

  Future<FestivalEventSchedule?> loadEventSchedule() => _eventSchedule.load();

  /// 이벤트 모드에서 추천 공개 전이면 웨이팅 화면에 머물러야 함.
  Future<bool> isWaitingForRecommendationReveal() async {
    final schedule = await _eventSchedule.load();
    return schedule != null &&
        schedule.enabled &&
        !schedule.areRecommendationsRevealed();
  }

  Future<String> matchesOrWaitingRoute() async {
    if (await isWaitingForRecommendationReveal()) {
      return AppRoutes.waiting;
    }
    return AppRoutes.matches;
  }

  Future<void> _ensureProfileTasteOpen() async {
    final schedule = await _eventSchedule.load();
    if (schedule != null && schedule.isProfileTasteLocked()) {
      throw FestivalBackendException(
        '프로필 작성·취향 학습이 ${schedule.formatClockKst(schedule.profileTasteLockAt)}에 마감되었어요.',
      );
    }
  }

  Future<void> _ensureRecommendationsRevealed() async {
    final schedule = await _eventSchedule.load();
    if (schedule != null && !schedule.areRecommendationsRevealed()) {
      throw FestivalBackendException(
        '추천 결과는 ${schedule.formatClockKst(schedule.recommendationsRevealAt)}에 공개됩니다.',
      );
    }
  }

  bool get isAuthenticated => _session?.isActive ?? false;
  FestivalSession? get session => _session?.isActive == true ? _session : null;

  Future<void> configureAuthPersistence() async {
    if (!kIsWeb) return;

    try {
      await _auth.setPersistence(Persistence.LOCAL);
    } catch (_) {
      // Safari private mode or blocked storage can reject persistence setup.
      // In that case Firebase still falls back to the browser's available mode.
    }
  }

  Future<void> restoreSession() async {
    final user = await _currentUserAfterAuthRestore();
    if (user == null) return;

    try {
      final snapshot = await _db
          .collection('festivalSessions')
          .doc(user.uid)
          .get();
      final data = snapshot.data();
      if (data == null) return;

      final restored = FestivalSession.fromMap(data);
      if (restored.isActive) {
        if (await _isTicketDisabled(restored.ticketId)) {
          await _db.collection('festivalSessions').doc(user.uid).delete();
          await _auth.signOut();
          _session = null;
          return;
        }
        _session = restored;
      }
    } catch (_) {
      _session = null;
    }
  }

  Future<void> logout() async {
    final activeSession = _session;
    _session = null;
    await FestivalPushService.instance.disableCurrentToken();

    try {
      final currentUser = _auth.currentUser;
      final uid = currentUser?.uid ?? activeSession?.uid;
      if (uid != null && uid.isNotEmpty) {
        await _db.collection('festivalSessions').doc(uid).delete();
      }
    } on FirebaseException {
      // Local logout should still proceed even if the remote session was
      // already gone or temporarily unavailable.
    }

    await _auth.signOut();
  }

  Future<User?> _currentUserAfterAuthRestore() async {
    final currentUser = _auth.currentUser;
    if (currentUser != null) return currentUser;

    try {
      return await _auth
          .authStateChanges()
          .firstWhere((user) => user != null)
          .timeout(
            const Duration(milliseconds: 1800),
            onTimeout: () => _auth.currentUser,
          );
    } catch (_) {
      return _auth.currentUser;
    }
  }

  Future<FestivalSession> redeemCode(String rawCode) async {
    final ticketId = _normalizeTicketCode(rawCode);
    if (ticketId.isEmpty) {
      throw const FestivalBackendException('입장 코드를 입력해주세요.');
    }

    final user = await _ensureUser();
    return _redeemTicket(ticketId: ticketId, user: user, source: 'code');
  }

  Future<FestivalSession> redeemQrToken(String token) async {
    return redeemCode(token);
  }

  Future<User> _ensureUser() async {
    final currentUser = _auth.currentUser;
    if (currentUser != null) return currentUser;

    try {
      final credential = await _auth.signInAnonymously();
      final user = credential.user;
      if (user == null) {
        throw const FestivalBackendException('익명 인증을 시작하지 못했어요.');
      }
      return user;
    } on FirebaseAuthException catch (error) {
      final message = (error.message ?? '').trim();
      if (error.code == 'operation-not-allowed' ||
          error.code == 'configuration-not-found' ||
          message == 'Error') {
        throw const FestivalBackendException(
          'Firebase Authentication에서 익명 로그인을 먼저 켜주세요.',
        );
      }
      throw FestivalBackendException('인증에 실패했어요. $message'.trim());
    } catch (_) {
      throw const FestivalBackendException(
        'Firebase Authentication 익명 로그인 설정을 확인해주세요.',
      );
    }
  }

  Future<FestivalSession> _redeemTicket({
    required String ticketId,
    required User user,
    required String source,
  }) async {
    if (await _isTicketDisabled(ticketId)) {
      throw const FestivalBackendException('신고 처리로 입장이 제한된 코드예요. 운영팀에 문의해주세요.');
    }

    final expiresAt = DateTime.now().add(_ticketSessionDuration);
    final ticketRef = _db.collection('festivalTickets').doc(ticketId);
    final sessionRef = _db.collection('festivalSessions').doc(user.uid);
    final session = FestivalSession(
      uid: user.uid,
      ticketId: ticketId,
      code: ticketId,
      sessionExpiresAt: expiresAt,
    );

    try {
      await _db.runTransaction((transaction) async {
        final ticketSnapshot = await transaction.get(ticketRef);
        final ticketData = <String, Object?>{
          'code': ticketId,
          'status': 'active',
          'round': 1,
          'lastUid': user.uid,
          'lastRedeemSource': source,
          'lastRedeemedAt': FieldValue.serverTimestamp(),
          'sessionExpiresAt': Timestamp.fromDate(expiresAt),
          'updatedAt': FieldValue.serverTimestamp(),
        };

        if (!ticketSnapshot.exists) {
          ticketData['createdAt'] = FieldValue.serverTimestamp();
        }

        transaction.set(ticketRef, ticketData, SetOptions(merge: true));
        transaction.set(sessionRef, {
          'uid': user.uid,
          'ticketId': ticketId,
          'code': ticketId,
          'sessionExpiresAt': Timestamp.fromDate(expiresAt),
          'updatedAt': FieldValue.serverTimestamp(),
        }, SetOptions(merge: true));
      });
    } on FirebaseException catch (error) {
      throw FestivalBackendException(_firestoreMessage(error));
    }

    _session = session;
    await FestivalPushService.instance.syncTokenSafely();
    return session;
  }

  Future<FestivalProfile?> profileForChatRoom(String roomId) async {
    final activeSession = session;
    if (activeSession == null || roomId.isEmpty) return null;

    try {
      final snapshot = await _chatMembershipRef(
        activeSession.ticketId,
        roomId,
      ).get();
      if (!snapshot.exists) return null;
      final data = snapshot.data();
      if (data == null) return null;

      final counterpartTicketId = data['counterpartTicketId'] as String? ?? '';
      if (counterpartTicketId.isEmpty) return null;

      final profile = data['counterpartProfile'];
      final profileData = profile is Map
          ? Map<String, dynamic>.from(profile)
          : <String, dynamic>{};
      return _festivalProfileFromChatSnapshot(counterpartTicketId, profileData);
    } catch (_) {
      return null;
    }
  }

  Future<void> saveProfile(Map<String, Object?> profileData) async {
    await _ensureProfileTasteOpen();
    final activeSession = _requireSession();
    final profileRef = _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId);
    final ticketRef = _db
        .collection('festivalTickets')
        .doc(activeSession.ticketId);

    await profileRef.set({
      ...profileData,
      'uid': activeSession.uid,
      'ticketId': activeSession.ticketId,
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    await ticketRef.set({
      'profileDraft': FieldValue.delete(),
      'profileCompleted': true,
      'profileCompletedAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  Future<ProfileDraft?> loadProfileDraft() async {
    final activeSession = _requireSession();

    try {
      final snapshot = await _db
          .collection('festivalTickets')
          .doc(activeSession.ticketId)
          .get();
      final data = snapshot.data();
      final draft = data?['profileDraft'];
      if (draft is! Map) return null;
      return ProfileDraft.fromMap(Map<String, dynamic>.from(draft));
    } on FirebaseException catch (error) {
      throw FestivalBackendException(_progressMessage(error));
    }
  }

  Future<void> saveProfileDraft(Map<String, Object?> draftData) async {
    await _ensureProfileTasteOpen();
    final activeSession = _requireSession();
    await _db.collection('festivalTickets').doc(activeSession.ticketId).set({
      'code': activeSession.ticketId,
      'lastUid': activeSession.uid,
      'profileDraft': {...draftData, 'updatedAt': FieldValue.serverTimestamp()},
      'profileDraftUpdatedAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
  }

  Future<void> recordTasteSwipe({
    required int index,
    required TasteCardData card,
    required bool liked,
  }) async {
    await _ensureProfileTasteOpen();
    final activeSession = _requireSession();
    final swipeId = index.toString().padLeft(2, '0');
    await _db
        .collection('festivalTickets')
        .doc(activeSession.ticketId)
        .collection('tasteSwipes')
        .doc(swipeId)
        .set({
          'index': index,
          'cardId': card.id,
          'aiProfileNumber': card.number,
          'aiProfileCode': card.code,
          'cardImagePath': card.imagePath,
          'cardGender': card.gender,
          'reaction': liked ? 'like' : 'dislike',
          'reactionLabel': liked ? '좋아요' : '별로에요',
          'liked': liked,
          'createdAt': FieldValue.serverTimestamp(),
        }, SetOptions(merge: true));
  }

  Future<List<TasteCardData>> loadTasteCards() async {
    final activeSession = _requireSession();
    final profileSnapshot = await _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId)
        .get();
    final gender = profileSnapshot.data()?['gender'] as String?;
    if (gender == null || gender.isEmpty) {
      throw const FestivalBackendException('프로필 등록 후 취향 학습을 시작할 수 있어요.');
    }

    final targetGender = gender == '남성' ? 'female' : 'male';
    final filePrefix = targetGender == 'female' ? 'f' : 'm';
    final colors = [
      [const Color(0xFFFF8E9E), const Color(0xFFFFD1DC)],
      [const Color(0xFF34D399), const Color(0xFFA7F3D0)],
      [const Color(0xFF60A5FA), const Color(0xFFBFDBFE)],
      [const Color(0xFFF59E0B), const Color(0xFFFDE68A)],
      [const Color(0xFF8B5CF6), const Color(0xFFE9D5FF)],
    ];

    return Future.wait(
      List.generate(_tasteCardCount, (index) async {
        final number = index + 1;
        final imagePath = 'ai_profiles/$targetGender/$filePrefix$number.png';
        final imageUrl = await _storage.ref(imagePath).getDownloadURL();
        return TasteCardData(
          id: '$targetGender-$number',
          gender: targetGender,
          number: number,
          code: '$filePrefix$number',
          imagePath: imagePath,
          imageUrl: imageUrl,
          colors: colors[index % colors.length],
        );
      }),
    );
  }

  Future<void> completeTasteTraining({
    required int likedCount,
    required int total,
  }) async {
    await _ensureProfileTasteOpen();
    final activeSession = _requireSession();
    final builder = FestivalTasteAffinityBuilder(_db);
    final affinity = await builder.buildForTicket(activeSession.ticketId);
    await builder.persistForTicket(
      activeSession.ticketId,
      affinities: affinity.affinities,
      preferenceVector: affinity.preferenceVector,
    );
    await _db.collection('festivalTickets').doc(activeSession.ticketId).set({
      'tasteCompleted': true,
      'tasteCompletedAt': FieldValue.serverTimestamp(),
      'tasteLikedCount': likedCount,
      'tasteTotalCount': total,
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));
    final schedule = await _eventSchedule.load();
    if (schedule == null || !schedule.enabled) {
      _runSilently(_refreshRecommendationsForTicket(activeSession.ticketId));
    }
  }

  Future<void> _refreshRecommendationsForTicket(String ticketId) async {
    final profileSnap = await _db
        .collection('festivalProfiles')
        .doc(ticketId)
        .get();
    final gender = profileSnap.data()?['gender'] as String?;
    if (gender == null || gender.isEmpty) return;
    final engine = FestivalRecommendationEngine(_db);
    final result = await engine.generateLive(
      ticketId: ticketId,
      currentGender: gender,
      targetGender: gender == '남성' ? '여성' : '남성',
    );
    await _persistRecommendationResult(ticketId, result);
  }

  Future<void> _persistRecommendationResult(
    String ticketId,
    FestivalRecommendationResult result,
  ) async {
    final dateKey = FestivalRecommendationEngine(_db).kstDateKey();
    final items = <Map<String, Object?>>[];
    for (final slot in result.slots) {
      if (slot == null) continue;
      items.add({
        'ticketId': slot.ticketId,
        'uid': slot.ticketId,
        'rank': items.length + 1,
        'score': slot.score,
      });
    }
    if (items.isEmpty) return;

    await _db
        .collection('festivalModelRecs')
        .doc(ticketId)
        .collection('daily')
        .doc(dateKey)
        .collection('sources')
        .doc('clip')
        .set({
          'status': 'ready',
          'algorithmVersion': 'festival_clip_web_v1',
          'model': {'type': 'clip', 'source': 'festival_web_live'},
          'generatedAt': FieldValue.serverTimestamp(),
          'topN': items.length,
          'items': items,
        }, SetOptions(merge: true));
  }

  Future<FestivalOnboardingProgress> loadOnboardingProgress() async {
    final activeSession = _requireSession();
    final ticketRef = _db
        .collection('festivalTickets')
        .doc(activeSession.ticketId);

    try {
      final ticketSnapshot = await ticketRef.get();
      final ticketData = ticketSnapshot.data() ?? <String, dynamic>{};
      final profileSnapshot = await _db
          .collection('festivalProfiles')
          .doc(activeSession.ticketId)
          .get();
      final profileData = profileSnapshot.data();
      final profileCompleted =
          ticketData['profileCompleted'] == true ||
          _profileLooksComplete(profileData);

      if (!profileCompleted) {
        return const FestivalOnboardingProgress(
          nextStep: FestivalNextStep.profile,
        );
      }

      final swipesSnapshot = await ticketRef.collection('tasteSwipes').get();
      final answeredIndexes = <int>{};
      var likedCount = 0;

      for (final doc in swipesSnapshot.docs) {
        final data = doc.data();
        final index = _readSwipeIndex(data, doc.id);
        if (index == null || index < 0 || index >= _tasteCardCount) continue;
        answeredIndexes.add(index);
        if (data['liked'] == true) likedCount += 1;
      }

      final nextTasteIndex = _nextTasteIndex(answeredIndexes);
      final tasteCompleted =
          ticketData['tasteCompleted'] == true ||
          nextTasteIndex >= _tasteCardCount;

      if (tasteCompleted) {
        if (ticketData['tasteCompleted'] != true) {
          final schedule = await _eventSchedule.load();
          if (schedule == null || !schedule.isProfileTasteLocked()) {
            _runSilently(
              ticketRef.set({
                'tasteCompleted': true,
                'tasteCompletedAt': FieldValue.serverTimestamp(),
                'tasteLikedCount': likedCount,
                'tasteTotalCount': _tasteCardCount,
                'updatedAt': FieldValue.serverTimestamp(),
              }, SetOptions(merge: true)),
            );
          }
        }
        return FestivalOnboardingProgress(
          nextStep: FestivalNextStep.waiting,
          completedTasteCount: answeredIndexes.length,
          likedTasteCount: likedCount,
          nextTasteIndex: _tasteCardCount,
        );
      }

      return FestivalOnboardingProgress(
        nextStep: FestivalNextStep.taste,
        completedTasteCount: answeredIndexes.length,
        likedTasteCount: likedCount,
        nextTasteIndex: nextTasteIndex,
      );
    } on FirebaseException catch (error) {
      throw FestivalBackendException(_progressMessage(error));
    }
  }

  Future<RecommendationBundle> loadPersonalizedRecommendations({
    bool refreshOnServer = false,
  }) async {
    await _ensureRecommendationsRevealed();
    final activeSession = _requireSession();
    final currentProfile = await _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId)
        .get();
    final currentData = currentProfile.data();
    final currentGender = currentData?['gender'] as String?;
    if (currentData == null || currentGender == null || currentGender.isEmpty) {
      throw const FestivalBackendException('프로필 등록 후 추천을 확인할 수 있어요.');
    }

    if (refreshOnServer) {
      final schedule = await _eventSchedule.load();
      if (schedule?.enabled == true) {
        throw const FestivalBackendException('이벤트 모드에서는 추천이 일정에 맞춰 일괄 공개됩니다.');
      }
      await _requestServerRecommendationRefresh();
    }

    final targetGender = currentGender == '남성' ? '여성' : '남성';

    const palettes = [
      [Color(0xFFFF8E9E), Color(0xFFFFD1DC)],
      [Color(0xFF60A5FA), Color(0xFFBAE6FD)],
      [Color(0xFF8B5CF6), Color(0xFFE9D5FF)],
      [Color(0xFF34D399), Color(0xFFA7F3D0)],
      [Color(0xFFF59E0B), Color(0xFFFDE68A)],
    ];

    // Try reading from festivalRecommendations/{ticketId} first
    final recSnap = await _db
        .collection('festivalRecommendations')
        .doc(activeSession.ticketId)
        .get();

    if (recSnap.exists) {
      final recData = recSnap.data() ?? <String, dynamic>{};
      final recs = recData['recommendations'] as List<dynamic>? ?? [];
      final slots = <FestivalProfile?>[];

      for (var i = 0; i < recs.length && i < 3; i++) {
        final rec = recs[i] as Map<String, dynamic>? ?? <String, dynamic>{};
        final recTicketId = rec['ticketId'] as String? ?? '';
        if (recTicketId.isEmpty) {
          slots.add(null);
          continue;
        }
        // Load fresh profile data to get latest photoUrl
        final profileSnap = await _db
            .collection('festivalProfiles')
            .doc(recTicketId)
            .get();
        if (!profileSnap.exists) {
          slots.add(null);
          continue;
        }
        final matchPercent = rec['matchPercent'] as int? ?? 80;
        slots.add(
          FestivalProfile.fromSnapshot(
            profileSnap,
            matchPercent: matchPercent,
            colors: palettes[i % palettes.length],
          ),
        );
      }

      while (slots.length < 3) {
        slots.add(null);
      }

      final availableCount = recData['totalCandidates'] as int? ?? 0;

      return RecommendationBundle(
        currentGender: currentGender,
        targetGender: targetGender,
        availableCount: availableCount,
        slots: slots,
      );
    }

    // Fall back to legacy festivalModelRecs-based engine
    final engine = FestivalRecommendationEngine(_db);
    final result = await engine.loadRecommendations(
      ticketId: activeSession.ticketId,
      currentGender: currentGender,
    );

    final slots = <FestivalProfile?>[];
    for (var index = 0; index < result.slots.length; index++) {
      final slot = result.slots[index];
      if (slot == null) {
        slots.add(null);
        continue;
      }
      final snap = await _db
          .collection('festivalProfiles')
          .doc(slot.ticketId)
          .get();
      if (!snap.exists) {
        slots.add(null);
        continue;
      }
      slots.add(
        FestivalProfile.fromSnapshot(
          snap,
          matchPercent: slot.matchPercent,
          colors: palettes[index % palettes.length],
        ),
      );
    }
    while (slots.length < 3) {
      slots.add(null);
    }

    return RecommendationBundle(
      currentGender: result.currentGender,
      targetGender: result.targetGender,
      availableCount: result.availableCount,
      slots: slots,
    );
  }

  Future<void> _ensureFestivalEmbeddingsSeeded() async {
    final aiSample = await _db
        .collection('festivalAiEmbeddings')
        .doc('f1')
        .get();
    if (aiSample.exists) return;

    debugPrint(
      '[FestivalBackend] festivalAiEmbeddings missing — running seed…',
    );
    try {
      final seedCallable =
          FirebaseFunctions.instanceFor(
            region: 'asia-northeast3',
          ).httpsCallable(
            'seedFestivalEmbeddings',
            options: HttpsCallableOptions(
              timeout: const Duration(seconds: 540),
            ),
          );
      final result = await seedCallable.call();
      debugPrint('[FestivalBackend] seedFestivalEmbeddings: $result');
    } on FirebaseFunctionsException catch (e) {
      debugPrint(
        '[FestivalBackend] seed error: ${e.code} ${e.message} ${e.details}',
      );
      throw FestivalBackendException(
        e.message?.isNotEmpty == true
            ? 'CLIP 임베딩 준비에 실패했어요. ${e.message}'
            : 'CLIP 임베딩 준비에 실패했어요. 잠시 후 다시 시도해주세요.',
      );
    }
  }

  Future<void> _requestServerRecommendationRefresh() async {
    try {
      await _ensureFestivalEmbeddingsSeeded();
      final callable = FirebaseFunctions.instanceFor(region: 'asia-northeast3')
          .httpsCallable(
            'refreshFestivalRecommendations',
            options: HttpsCallableOptions(
              timeout: const Duration(seconds: 120),
            ),
          );
      await callable.call();
    } on FirebaseFunctionsException catch (e) {
      debugPrint(
        '[FestivalBackend] callable error: ${e.code} ${e.message} ${e.details}',
      );
      throw FestivalBackendException(
        e.message?.isNotEmpty == true
            ? '추천 계산에 실패했어요. ${e.message}'
            : '추천 계산에 실패했어요.',
      );
    }
  }

  Future<void> saveChatMessage(FestivalProfile profile, String text) async {
    final activeSession = _requireSession();
    final roomId = _festivalChatRoomId(activeSession.ticketId, profile.id);
    await _ensureChatRoom(profile);
    final chatRef = _db.collection('festivalChatRooms').doc(roomId);
    final messageRef = chatRef.collection('messages').doc();
    final currentProfile = await _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId)
        .get();
    final currentProfileData = currentProfile.data() ?? <String, dynamic>{};
    final counterpartTicket = await _db
        .collection('festivalTickets')
        .doc(profile.id)
        .get();
    final counterpartUid =
        counterpartTicket.data()?['lastUid'] as String? ?? '';
    final participantUids = [
      activeSession.uid,
      if (counterpartUid.isNotEmpty) counterpartUid,
    ];
    final unreadFor = <String, Object?>{};
    if (counterpartUid.isNotEmpty && counterpartUid != activeSession.uid) {
      unreadFor[counterpartUid] = true;
    }
    final participantTicketIds = [activeSession.ticketId, profile.id];
    final activeProfileSnapshot = _chatProfileSnapshot(
      activeSession.ticketId,
      currentProfileData,
    );
    final counterpartProfileSnapshot = _chatProfileSnapshotFromProfile(profile);
    final timestamp = FieldValue.serverTimestamp();

    final batch = _db.batch();
    batch.set(chatRef, {
      'roomId': roomId,
      'participantTicketIds': participantTicketIds,
      'participantUids': participantUids,
      'participantProfiles': {
        activeSession.ticketId: activeProfileSnapshot,
        profile.id: counterpartProfileSnapshot,
      },
      'latestMessage': text,
      'latestMessageAt': timestamp,
      'lastSenderUid': activeSession.uid,
      if (unreadFor.isNotEmpty) 'unreadFor': unreadFor,
      'updatedAt': timestamp,
    }, SetOptions(merge: true));

    batch.set(messageRef, {
      'senderUid': activeSession.uid,
      'senderTicketId': activeSession.ticketId,
      'receiverTicketId': profile.id,
      'text': text,
      'createdAt': timestamp,
      'readBy': [activeSession.uid],
    });

    batch.set(
      _chatMembershipRef(activeSession.ticketId, roomId),
      _chatMembershipData(
        roomId: roomId,
        ownerTicketId: activeSession.ticketId,
        counterpartTicketId: profile.id,
        participantTicketIds: participantTicketIds,
        counterpartProfile: counterpartProfileSnapshot,
        latestMessage: text,
        unread: false,
        timestamp: timestamp,
      ),
      SetOptions(merge: true),
    );
    batch.set(
      _chatMembershipRef(profile.id, roomId),
      _chatMembershipData(
        roomId: roomId,
        ownerTicketId: profile.id,
        counterpartTicketId: activeSession.ticketId,
        participantTicketIds: participantTicketIds,
        counterpartProfile: activeProfileSnapshot,
        latestMessage: text,
        unread: true,
        timestamp: timestamp,
      ),
      SetOptions(merge: true),
    );

    await batch.commit();
  }

  Stream<List<ChatPreview>> watchChatPreviews() {
    final activeSession = _requireSession();
    return _db
        .collection('festivalChatMemberships')
        .doc(activeSession.ticketId)
        .collection('rooms')
        .snapshots()
        .map((snapshot) {
          final previews = <ChatPreview>[];
          for (final doc in snapshot.docs) {
            try {
              previews.add(ChatPreview.fromMembershipDoc(doc));
            } catch (_) {
              // Ignore malformed room documents while keeping the list usable.
            }
          }
          previews.sort((a, b) {
            if (a.unreadCount != b.unreadCount) {
              return b.unreadCount.compareTo(a.unreadCount);
            }
            return b.lastMessageAt.compareTo(a.lastMessageAt);
          });
          return previews;
        });
  }

  Stream<List<ChatMessage>> watchChatMessages(FestivalProfile profile) {
    final activeSession = _requireSession();
    final roomId = _festivalChatRoomId(activeSession.ticketId, profile.id);
    return Stream.fromFuture(_ensureChatRoom(profile)).asyncExpand((_) {
      return _db
          .collection('festivalChatRooms')
          .doc(roomId)
          .collection('messages')
          .orderBy('createdAt', descending: true)
          .snapshots()
          .map(
            (snapshot) => snapshot.docs
                .map(
                  (doc) => ChatMessage.fromMessageDoc(
                    doc,
                    currentTicketId: activeSession.ticketId,
                    currentUid: activeSession.uid,
                  ),
                )
                .toList(),
          );
    });
  }

  Future<void> markChatRead(FestivalProfile profile) async {
    final activeSession = _requireSession();
    final roomId = _festivalChatRoomId(activeSession.ticketId, profile.id);
    try {
      await _chatMembershipRef(
        activeSession.ticketId,
        roomId,
      ).update({'unread': false, 'updatedAt': FieldValue.serverTimestamp()});
    } on FirebaseException catch (error) {
      if (error.code != 'not-found' && error.code != 'permission-denied') {
        rethrow;
      }
    }

    try {
      await _db.collection('festivalChatRooms').doc(roomId).update({
        'unreadFor.${activeSession.uid}': false,
        'updatedAt': FieldValue.serverTimestamp(),
      });
    } on FirebaseException catch (error) {
      if (error.code != 'not-found' && error.code != 'permission-denied') {
        rethrow;
      }
    }
  }

  Future<void> _ensureChatRoom(FestivalProfile profile) async {
    final activeSession = _requireSession();
    if (profile.id.isEmpty) {
      throw const FestivalBackendException('상대 프로필 정보를 찾지 못했어요.');
    }

    final roomId = _festivalChatRoomId(activeSession.ticketId, profile.id);
    final currentProfile = await _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId)
        .get();
    final currentProfileData = currentProfile.data() ?? <String, dynamic>{};
    final counterpartTicket = await _db
        .collection('festivalTickets')
        .doc(profile.id)
        .get();
    final counterpartUid =
        counterpartTicket.data()?['lastUid'] as String? ?? '';
    final participantTicketIds = [activeSession.ticketId, profile.id];
    final participantUids = [
      activeSession.uid,
      if (counterpartUid.isNotEmpty) counterpartUid,
    ];

    try {
      await _db.collection('festivalChatRooms').doc(roomId).set({
        'roomId': roomId,
        'participantTicketIds': participantTicketIds,
        'participantUids': participantUids,
        'participantProfiles': {
          activeSession.ticketId: _chatProfileSnapshot(
            activeSession.ticketId,
            currentProfileData,
          ),
          profile.id: _chatProfileSnapshotFromProfile(profile),
        },
        'updatedAt': FieldValue.serverTimestamp(),
      }, SetOptions(merge: true));
    } on FirebaseException catch (error) {
      throw FestivalBackendException(_firestoreMessage(error));
    }
  }

  Future<void> submitUserReport({
    required FestivalProfile reportedProfile,
    required String reason,
    required String source,
    String? roomId,
    String? details,
  }) async {
    final activeSession = _requireSession();
    if (reportedProfile.id.isEmpty ||
        reportedProfile.id == activeSession.ticketId) {
      throw const FestivalBackendException('신고할 수 없는 프로필이에요.');
    }

    final trimmedReason = reason.trim();
    if (trimmedReason.isEmpty) {
      throw const FestivalBackendException('신고 사유를 선택해주세요.');
    }

    final reporterProfile = await _db
        .collection('festivalProfiles')
        .doc(activeSession.ticketId)
        .get();
    final reporterData = reporterProfile.data() ?? <String, dynamic>{};

    try {
      await _db.collection('festivalDeveloperReports').add({
        'status': 'open',
        'source': source,
        'reason': trimmedReason,
        if (details?.trim().isNotEmpty == true) 'details': details!.trim(),
        'reporterTicketId': activeSession.ticketId,
        'reporterUid': activeSession.uid,
        'reportedTicketId': reportedProfile.id,
        'reportedProfileSnapshot': _chatProfileSnapshotFromProfile(
          reportedProfile,
        ),
        'reporterProfileSnapshot': _chatProfileSnapshot(
          activeSession.ticketId,
          reporterData,
        ),
        if (roomId != null && roomId.isNotEmpty) 'roomId': roomId,
        'createdAt': FieldValue.serverTimestamp(),
        'updatedAt': FieldValue.serverTimestamp(),
      });
    } on FirebaseException catch (error) {
      throw FestivalBackendException(_firestoreMessage(error));
    }
  }

  Future<bool> _isTicketDisabled(String ticketId) async {
    if (ticketId.isEmpty) return false;

    try {
      final snapshot = await _db
          .collection('festivalTicketEnforcement')
          .doc(ticketId)
          .get();
      return snapshot.data()?['disabled'] == true;
    } on FirebaseException {
      return false;
    }
  }

  Stream<bool> watchCurrentTicketDisabled() {
    final activeSession = session;
    if (activeSession == null) {
      return Stream<bool>.value(false);
    }

    return _db
        .collection('festivalTicketEnforcement')
        .doc(activeSession.ticketId)
        .snapshots()
        .map((snapshot) => snapshot.data()?['disabled'] == true);
  }

  String? chatRoomIdFor(FestivalProfile profile) {
    final activeSession = session;
    if (activeSession == null || profile.id.isEmpty) return null;
    return _festivalChatRoomId(activeSession.ticketId, profile.id);
  }

  DocumentReference<Map<String, dynamic>> _chatMembershipRef(
    String ticketId,
    String roomId,
  ) {
    return _db
        .collection('festivalChatMemberships')
        .doc(ticketId)
        .collection('rooms')
        .doc(roomId);
  }

  Map<String, Object?> _chatMembershipData({
    required String roomId,
    required String ownerTicketId,
    required String counterpartTicketId,
    required List<String> participantTicketIds,
    required Map<String, Object?> counterpartProfile,
    required String latestMessage,
    required bool unread,
    required FieldValue timestamp,
  }) {
    return {
      'roomId': roomId,
      'ownerTicketId': ownerTicketId,
      'counterpartTicketId': counterpartTicketId,
      'participantTicketIds': participantTicketIds,
      'counterpartProfile': counterpartProfile,
      'latestMessage': latestMessage,
      'latestMessageAt': timestamp,
      'unread': unread,
      'updatedAt': timestamp,
    };
  }

  FestivalSession _requireSession() {
    final activeSession = session;
    if (activeSession == null) {
      throw const FestivalBackendException('입장 코드 인증 후 이용할 수 있어요.');
    }
    return activeSession;
  }

  bool _profileLooksComplete(Map<String, dynamic>? data) {
    if (data == null) return false;
    final nickname = data['nickname'] as String?;
    final gender = data['gender'] as String?;
    final department = data['department'] as String?;
    final studentAffiliation = data['studentAffiliation'] as String?;
    final mbti = data['mbti'] as String?;
    final photoUrl = FestivalAvatarDisplayResolver.resolve(data);
    return nickname?.trim().isNotEmpty == true &&
        gender?.trim().isNotEmpty == true &&
        department?.trim().isNotEmpty == true &&
        studentAffiliation?.trim().isNotEmpty == true &&
        data['age'] is int &&
        mbti?.trim().length == 4 &&
        photoUrl.trim().isNotEmpty;
  }

  int? _readSwipeIndex(Map<String, dynamic> data, String docId) {
    final storedIndex = data['index'];
    if (storedIndex is int) return storedIndex;
    return int.tryParse(docId);
  }

  int _nextTasteIndex(Set<int> answeredIndexes) {
    for (var index = 0; index < _tasteCardCount; index += 1) {
      if (!answeredIndexes.contains(index)) return index;
    }
    return _tasteCardCount;
  }

  String _firestoreMessage(FirebaseException error) {
    if (error.code == 'permission-denied') {
      return 'Firestore 접근 권한이 없어요. 입장 코드를 다시 확인하거나 잠시 후 다시 시도해주세요.';
    }
    if (error.code == 'not-found') {
      return '입장 코드 정보를 찾지 못했어요.';
    }
    return '입장 코드 확인에 실패했어요. ${error.message ?? ''}'.trim();
  }

  String _progressMessage(FirebaseException error) {
    if (error.code == 'permission-denied') {
      return '저장된 진행 상태를 읽을 권한이 없어요. 입장 코드를 다시 확인해주세요.';
    }
    return '진행 상태를 불러오지 못했어요. ${error.message ?? ''}'.trim();
  }

  String _festivalChatRoomId(String ticketIdA, String ticketIdB) {
    final ids = [ticketIdA, ticketIdB]..sort();
    return 'festival_${ids[0]}_${ids[1]}';
  }

  Map<String, Object?>? _approvedAvatarSnapshot(String? photoUrl) {
    final safeUrl = photoUrl?.trim() ?? '';
    if (safeUrl.isEmpty ||
        !FestivalAvatarDisplayResolver.isSafeDisplayUrl(safeUrl)) {
      return null;
    }
    return {'status': 'approved', 'approvedAvatarUrl': safeUrl};
  }

  Map<String, Object?> _chatProfileSnapshot(
    String ticketId,
    Map<String, dynamic> data,
  ) {
    final photoUrl = FestivalAvatarDisplayResolver.resolve(data);
    return {
      'id': ticketId,
      'name': data['nickname'] as String? ?? '익명',
      'age': data['age'] is int ? data['age'] as int : 20,
      'gender': data['gender'] as String? ?? '',
      'department': data['department'] as String? ?? '',
      'studentAffiliation': data['studentAffiliation'] as String?,
      'mbti': data['mbti'] as String? ?? '',
      'intro': data['intro'] as String? ?? '',
      'photoUrl': photoUrl.isEmpty ? null : photoUrl,
      'avatar': _approvedAvatarSnapshot(photoUrl),
    };
  }

  Map<String, Object?> _chatProfileSnapshotFromProfile(
    FestivalProfile profile,
  ) {
    return {
      'id': profile.id,
      'name': profile.name,
      'age': profile.age,
      'gender': profile.gender,
      'department': profile.department,
      'studentAffiliationLabel': profile.studentAffiliationLabel,
      'mbti': profile.mbti,
      'intro': profile.intro,
      'photoUrl': profile.photoUrl,
      'avatar': _approvedAvatarSnapshot(profile.photoUrl),
    };
  }
}

class AuthGate extends StatefulWidget {
  final Widget child;

  const AuthGate({super.key, required this.child});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  StreamSubscription<bool>? _enforcementSubscription;
  bool _isHandlingBan = false;

  @override
  void initState() {
    super.initState();
    _enforcementSubscription = FestivalBackend.instance
        .watchCurrentTicketDisabled()
        .listen(_handleEnforcement);
    if (FestivalBackend.instance.isAuthenticated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        FestivalPushService.instance.syncTokenSafely();
      });
    }
  }

  Future<void> _handleEnforcement(bool disabled) async {
    if (!disabled || _isHandlingBan || !mounted) return;
    _isHandlingBan = true;
    await FestivalBackend.instance.logout();
    if (!mounted) return;
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(AppRoutes.access, (route) => false);
    showAppSnack(context, '신고 처리로 입장이 제한되었어요. 운영팀에 문의해주세요.');
    _isHandlingBan = false;
  }

  @override
  void dispose() {
    _enforcementSubscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (FestivalBackend.instance.isAuthenticated) return widget.child;
    return const AccessScreen(message: '입장 코드 인증 후 이용할 수 있어요.');
  }
}

class FestivalEntryScreen extends StatelessWidget {
  const FestivalEntryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    if (Firebase.apps.isEmpty) {
      return const AccessScreen();
    }

    if (FestivalBackend.instance.isAuthenticated) {
      return const OnboardingRedirectScreen();
    }

    return const AccessScreen();
  }
}

class FestivalProfile {
  final String id;
  final String name;
  final int age;
  final String gender;
  final String department;
  final String studentAffiliationLabel;
  final String mbti;
  final String intro;
  final int matchPercent;
  final List<String> tags;
  final List<Color> colors;
  final String? photoUrl;

  const FestivalProfile({
    this.id = '',
    required this.name,
    required this.age,
    required this.gender,
    required this.department,
    required this.studentAffiliationLabel,
    required this.mbti,
    required this.intro,
    required this.matchPercent,
    required this.tags,
    required this.colors,
    this.photoUrl,
  });

  factory FestivalProfile.fromSnapshot(
    DocumentSnapshot<Map<String, dynamic>> doc, {
    required int matchPercent,
    required List<Color> colors,
  }) {
    final data = doc.data() ?? <String, dynamic>{};
    final photoUrl = FestivalAvatarDisplayResolver.resolve(data);
    return FestivalProfile(
      id: doc.id,
      name: (data['nickname'] as String?)?.trim().isNotEmpty == true
          ? data['nickname'] as String
          : '익명',
      age: data['age'] is int ? data['age'] as int : 20,
      gender: data['gender'] as String? ?? '',
      department: data['department'] as String? ?? '',
      studentAffiliationLabel: _studentAffiliationText(
        data['studentAffiliation'] as String?,
      ),
      mbti: data['mbti'] as String? ?? '',
      intro: (data['intro'] as String?)?.trim().isNotEmpty == true
          ? data['intro'] as String
          : '아직 자기소개를 적지 않았어요.',
      matchPercent: matchPercent,
      tags: const [],
      colors: colors,
      photoUrl: photoUrl.isEmpty ? null : photoUrl,
    );
  }

  factory FestivalProfile.fromProfileDoc(
    QueryDocumentSnapshot<Map<String, dynamic>> doc, {
    required int matchPercent,
    required List<Color> colors,
  }) {
    return FestivalProfile.fromSnapshot(
      doc,
      matchPercent: matchPercent,
      colors: colors,
    );
  }
}

String _studentAffiliationText(String? value) {
  if (value == 'yonsei') return '연세대 학생이에요';
  if (value == 'other') return '타 대학 학생이에요';
  return '소속 미입력';
}

class RecommendationBundle {
  final String currentGender;
  final String targetGender;
  final int availableCount;
  final List<FestivalProfile?> slots;

  const RecommendationBundle({
    required this.currentGender,
    required this.targetGender,
    required this.availableCount,
    required this.slots,
  });
}

enum FestivalNextStep { profile, taste, waiting }

class TasteTrainingResume {
  final int nextIndex;
  final int likedCount;

  const TasteTrainingResume({
    required this.nextIndex,
    required this.likedCount,
  });
}

class FestivalOnboardingProgress {
  final FestivalNextStep nextStep;
  final int completedTasteCount;
  final int likedTasteCount;
  final int nextTasteIndex;

  const FestivalOnboardingProgress({
    required this.nextStep,
    this.completedTasteCount = 0,
    this.likedTasteCount = 0,
    this.nextTasteIndex = 0,
  });

  TasteTrainingResume get tasteResume => TasteTrainingResume(
    nextIndex: nextTasteIndex,
    likedCount: likedTasteCount,
  );
}

const sampleProfiles = <FestivalProfile>[
  FestivalProfile(
    name: '서윤',
    age: 22,
    gender: '여성',
    department: '미디어커뮤니케이션학과',
    studentAffiliationLabel: '연세대 학생이에요',
    mbti: 'ENFP',
    intro: '축제 마지막 공연을 같이 보고, 끝나고 조용한 카페에서 이야기하는 걸 좋아해요.',
    matchPercent: 93,
    tags: ['밴드공연', '카페', '산책', '대화'],
    colors: [Color(0xFFFF8E9E), Color(0xFFFFD1DC)],
  ),
  FestivalProfile(
    name: '민지',
    age: 21,
    gender: '여성',
    department: '경영학과',
    studentAffiliationLabel: '연세대 학생이에요',
    mbti: 'ISFJ',
    intro: '사람 많은 곳도 좋지만 둘이 천천히 걷는 시간이 더 편해요.',
    matchPercent: 88,
    tags: ['푸드트럭', '야경', '사진', '잔잔함'],
    colors: [Color(0xFF60A5FA), Color(0xFFBAE6FD)],
  ),
  FestivalProfile(
    name: '하은',
    age: 23,
    gender: '여성',
    department: '컴퓨터공학과',
    studentAffiliationLabel: '타 대학 학생이에요',
    mbti: 'INTP',
    intro: '처음엔 조용하지만 관심사가 맞으면 오래 이야기하는 편이에요.',
    matchPercent: 84,
    tags: ['전시', '게임', '디저트', '새벽감성'],
    colors: [Color(0xFF8B5CF6), Color(0xFFE9D5FF)],
  ),
];

class AppViewport extends StatelessWidget {
  final Widget child;
  final double keyboardResizeFactor;

  const AppViewport({
    super.key,
    required this.child,
    this.keyboardResizeFactor = 0,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final pageWidth = math.min(constraints.maxWidth, _kMaxPageWidth);
        final isWide = constraints.maxWidth > _kMaxPageWidth;
        final keyboardBottom = MediaQuery.viewInsetsOf(context).bottom;
        final availableHeight = math.max(
          0.0,
          constraints.maxHeight - (keyboardBottom * keyboardResizeFactor),
        );
        final content = SizedBox(
          width: pageWidth,
          height: availableHeight,
          child: child,
        );

        return ColoredBox(
          color: isWide ? AppColors.desktopBackground : AppColors.background,
          child: Align(
            alignment: Alignment.topCenter,
            child: isWide
                ? DecoratedBox(
                    decoration: BoxDecoration(
                      color: AppColors.background,
                      border: Border.symmetric(
                        vertical: BorderSide(
                          color: AppColors.primary.withValues(alpha: 0.10),
                        ),
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.primary.withValues(alpha: 0.08),
                          blurRadius: 48,
                          offset: const Offset(0, 16),
                        ),
                      ],
                    ),
                    child: content,
                  )
                : content,
          ),
        );
      },
    );
  }
}

class AppScaffold extends StatelessWidget {
  final String? title;
  final Widget child;
  final Widget? bottomBar;
  final Widget? trailing;
  final bool showBack;
  final Color backgroundColor;
  final VoidCallback? onTitleTap;
  final bool resizeToAvoidBottomInset;
  final double keyboardResizeFactor;
  final double keyboardShiftFactor;
  final double bottomBarKeyboardPaddingFactor;

  const AppScaffold({
    super.key,
    required this.child,
    this.title,
    this.bottomBar,
    this.trailing,
    this.showBack = true,
    this.backgroundColor = AppColors.background,
    this.onTitleTap,
    this.resizeToAvoidBottomInset = false,
    this.keyboardResizeFactor = 0,
    this.keyboardShiftFactor = 0,
    this.bottomBarKeyboardPaddingFactor = 0,
  });

  @override
  Widget build(BuildContext context) {
    final keyboardShift =
        MediaQuery.viewInsetsOf(context).bottom * keyboardShiftFactor;
    final keyboardBottom = MediaQuery.viewInsetsOf(context).bottom;

    return AppViewport(
      keyboardResizeFactor: keyboardResizeFactor,
      child: Scaffold(
        resizeToAvoidBottomInset: resizeToAvoidBottomInset,
        backgroundColor: backgroundColor,
        body: SafeArea(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            transform: Matrix4.translationValues(0, -keyboardShift, 0),
            child: Column(
              children: [
                if (title != null || showBack || trailing != null)
                  _TopBar(
                    title: title ?? '',
                    showBack: showBack,
                    trailing: trailing,
                    onTitleTap: onTitleTap,
                  ),
                Expanded(child: child),
              ],
            ),
          ),
        ),
        bottomNavigationBar: bottomBar == null
            ? null
            : AnimatedPadding(
                duration: const Duration(milliseconds: 220),
                curve: Curves.easeOutCubic,
                padding: EdgeInsets.only(
                  bottom: keyboardBottom * bottomBarKeyboardPaddingFactor,
                ),
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: backgroundColor,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.04),
                        blurRadius: 18,
                        offset: const Offset(0, -8),
                      ),
                    ],
                  ),
                  child: SafeArea(
                    top: false,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
                      child: bottomBar,
                    ),
                  ),
                ),
              ),
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  final String title;
  final bool showBack;
  final Widget? trailing;
  final VoidCallback? onTitleTap;

  const _TopBar({
    required this.title,
    required this.showBack,
    this.trailing,
    this.onTitleTap,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          children: [
            SizedBox(
              width: 44,
              child: showBack && Navigator.of(context).canPop()
                  ? IconButton(
                      tooltip: '뒤로',
                      onPressed: () {
                        HapticFeedback.selectionClick();
                        Navigator.of(context).pop();
                      },
                      icon: const Icon(CupertinoIcons.chevron_back),
                      color: AppColors.textMain,
                    )
                  : null,
            ),
            Expanded(
              child: _TopBarTitle(title: title, onTap: onTitleTap),
            ),
            SizedBox(width: 44, child: trailing),
          ],
        ),
      ),
    );
  }
}

class _TopBarTitle extends StatelessWidget {
  final String title;
  final VoidCallback? onTap;

  const _TopBarTitle({required this.title, this.onTap});

  @override
  Widget build(BuildContext context) {
    final text = Center(
      child: Text(
        title,
        textAlign: TextAlign.center,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w800,
          color: AppColors.textMain,
          decoration: onTap == null
              ? TextDecoration.none
              : TextDecoration.underline,
          decorationColor: AppColors.textMain.withValues(alpha: 0.35),
        ),
      ),
    );

    if (onTap == null) return text;

    return Tooltip(
      message: '프로필 상세 보기',
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: text,
      ),
    );
  }
}

class FontMockupScreen extends StatelessWidget {
  const FontMockupScreen({super.key});

  static const _bodyFont = 'GriunGyuwon';
  static const _meongiFont = 'FestivalMeongiOutlineThick';
  static const _background = Color(0xFFFFF4F8);
  static const _surface = Color(0xFFFFFFFE);
  static const _surfaceSoft = Color(0xFFFFF8FB);
  static const _primary = Color(0xFFE7A5BF);
  static const _primaryDeep = Color(0xFFA7637C);
  static const _textMain = Color(0xFF4A313B);
  static const _textSub = Color(0xFF9A7785);
  static const _border = Color(0xFFF0DCE5);

  TextStyle get _heroStyle => const TextStyle(
    fontFamily: _bodyFont,
    fontSize: 38,
    height: 1.14,
    fontWeight: FontWeight.w700,
    color: _textMain,
  );

  TextStyle get _titleStyle => const TextStyle(
    fontFamily: _bodyFont,
    fontSize: 24,
    height: 1.18,
    fontWeight: FontWeight.w700,
    color: _textMain,
  );

  TextStyle get _cardTitleStyle => const TextStyle(
    fontFamily: _bodyFont,
    fontSize: 22,
    height: 1.18,
    fontWeight: FontWeight.w800,
    color: _textMain,
  );

  TextStyle get _bodyStyle => const TextStyle(
    fontFamily: _bodyFont,
    fontSize: 16,
    height: 1.52,
    fontWeight: FontWeight.w500,
    color: _textSub,
  );

  TextStyle get _smallStyle => const TextStyle(
    fontFamily: _bodyFont,
    fontSize: 13,
    height: 1.38,
    fontWeight: FontWeight.w600,
    color: _textSub,
  );

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = math.min(constraints.maxWidth, _kMaxPageWidth);

        return ColoredBox(
          color: _background,
          child: Align(
            alignment: Alignment.topCenter,
            child: SizedBox(
              width: width,
              height: constraints.maxHeight,
              child: Scaffold(
                backgroundColor: _background,
                body: SafeArea(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(22, 18, 22, 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Center(
                          child: Image.asset(
                            'assets/images/mainlogo.png',
                            width: 104,
                            fit: BoxFit.contain,
                          ),
                        ),
                        const SizedBox(height: 26),
                        SizedBox(
                          width: double.infinity,
                          child: FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text('축제에서 만나는 오늘의 인연!', style: _heroStyle),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Text('맞춤형 이상형 매칭 서비스 설레연입니다!', style: _bodyStyle),
                        const SizedBox(height: 24),
                        _MockCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  _MockIconBubble(
                                    icon: CupertinoIcons.qrcode_viewfinder,
                                  ),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Text(
                                      '1차 매칭권',
                                      style: _cardTitleStyle,
                                    ),
                                  ),
                                  _MockPill(text: '코드 확인'),
                                ],
                              ),
                              const SizedBox(height: 20),
                              Text('입장 코드', style: _smallStyle),
                              const SizedBox(height: 8),
                              _MockInput(
                                text: 'SLY-A8323A-6F7B2A',
                                fontFamily: _meongiFont,
                              ),
                              const SizedBox(height: 16),
                              _MockMetaRow(
                                icon: CupertinoIcons.clock,
                                label: '프로필 마감',
                                value: '19:30',
                              ),
                              const SizedBox(height: 9),
                              _MockMetaRow(
                                icon: CupertinoIcons.sparkles,
                                label: '결과 공개',
                                value: '20:00',
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 18),
                        _MockCard(
                          color: _surfaceSoft,
                          child: Row(
                            children: [
                              _MockIconBubble(
                                icon: CupertinoIcons.bell_fill,
                                color: _primary,
                              ),
                              const SizedBox(width: 13),
                              Expanded(
                                child: Text(
                                  '홈 화면에 추가하면 매칭 결과와 새 채팅 알림을 더 안정적으로 받을 수 있어요.',
                                  style: _bodyStyle.copyWith(
                                    color: _textMain,
                                    fontSize: 15,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 26),
                        Text('프로필 작성', style: _titleStyle),
                        const SizedBox(height: 12),
                        _MockCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              _MockField(label: '닉네임', value: '친구들이 부르는 이름'),
                              const SizedBox(height: 14),
                              Text('성별', style: _smallStyle),
                              const SizedBox(height: 8),
                              Row(
                                children: const [
                                  Expanded(child: _MockChoice(text: '남성')),
                                  SizedBox(width: 8),
                                  Expanded(child: _MockChoice(text: '여성')),
                                ],
                              ),
                              const SizedBox(height: 14),
                              _MockField(label: '학과', value: '예: 경영학과'),
                              const SizedBox(height: 14),
                              Text('MBTI', style: _smallStyle),
                              const SizedBox(height: 8),
                              Row(
                                children: const [
                                  _MockMbti(text: 'E'),
                                  _MockMbti(text: 'N'),
                                  _MockMbti(text: 'F'),
                                  _MockMbti(text: 'P'),
                                ],
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 26),
                        Text('오늘의 인연', style: _titleStyle),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 260,
                          child: Row(
                            children: [
                              Expanded(
                                flex: 5,
                                child: _MockProfileCard(
                                  name: '서윤',
                                  percent: '93%',
                                  color: const Color(0xFFF8C7D9),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                flex: 4,
                                child: Column(
                                  children: [
                                    Expanded(
                                      child: _MockProfileCard(
                                        name: '민지',
                                        percent: '88%',
                                        color: const Color(0xFFDCC8F4),
                                        compact: true,
                                      ),
                                    ),
                                    const SizedBox(height: 12),
                                    Expanded(
                                      child: _MockProfileCard(
                                        name: '하은',
                                        percent: '84%',
                                        color: const Color(0xFFFCE0EA),
                                        compact: true,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 22),
                        SizedBox(
                          width: double.infinity,
                          height: 58,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: _primary,
                              borderRadius: BorderRadius.circular(20),
                              boxShadow: [
                                BoxShadow(
                                  color: _primary.withValues(alpha: 0.16),
                                  blurRadius: 20,
                                  offset: const Offset(0, 10),
                                ),
                              ],
                            ),
                            child: Center(
                              child: Text(
                                '입장하기',
                                style: const TextStyle(
                                  fontFamily: _bodyFont,
                                  fontSize: 20,
                                  fontWeight: FontWeight.w700,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _MockCard extends StatelessWidget {
  final Widget child;
  final Color color;

  const _MockCard({
    required this.child,
    this.color = FontMockupScreen._surface,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: FontMockupScreen._border),
        boxShadow: [
          BoxShadow(
            color: FontMockupScreen._primary.withValues(alpha: 0.07),
            blurRadius: 26,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _MockIconBubble extends StatelessWidget {
  final IconData icon;
  final Color color;

  const _MockIconBubble({
    required this.icon,
    this.color = FontMockupScreen._primary,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 46,
      height: 46,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Icon(icon, color: color, size: 25),
    );
  }
}

class _MockPill extends StatelessWidget {
  final String text;

  const _MockPill({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: FontMockupScreen._primary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(99),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontFamily: FontMockupScreen._bodyFont,
          color: FontMockupScreen._primaryDeep,
          fontSize: 12,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _MockInput extends StatelessWidget {
  final String text;
  final String fontFamily;

  const _MockInput({
    required this.text,
    this.fontFamily = FontMockupScreen._bodyFont,
  });

  @override
  Widget build(BuildContext context) {
    final isMeongi = fontFamily == FontMockupScreen._meongiFont;

    return Container(
      height: 52,
      alignment: Alignment.centerLeft,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(17),
        border: Border.all(color: FontMockupScreen._border),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.visible,
        style: TextStyle(
          fontFamily: fontFamily,
          fontSize: isMeongi ? 25 : 15,
          height: 1.0,
          fontWeight: FontWeight.w600,
          color: FontMockupScreen._textSub,
        ),
      ),
    );
  }
}

class _MockMbtiGlyph extends StatelessWidget {
  final String text;

  const _MockMbtiGlyph({required this.text});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontFamily: FontMockupScreen._meongiFont,
        fontSize: 29,
        height: 1.0,
        fontWeight: FontWeight.w900,
        color: FontMockupScreen._primaryDeep,
      ),
    );
  }
}

class _MockMetaRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _MockMetaRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 17, color: FontMockupScreen._textSub),
        const SizedBox(width: 8),
        Text(
          label,
          style: const TextStyle(
            fontFamily: FontMockupScreen._bodyFont,
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: FontMockupScreen._textSub,
          ),
        ),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(
            fontFamily: FontMockupScreen._bodyFont,
            fontSize: 15,
            fontWeight: FontWeight.w800,
            color: FontMockupScreen._textMain,
          ),
        ),
      ],
    );
  }
}

class _MockField extends StatelessWidget {
  final String label;
  final String value;

  const _MockField({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontFamily: FontMockupScreen._bodyFont,
            fontSize: 13,
            fontWeight: FontWeight.w700,
            color: FontMockupScreen._textSub,
          ),
        ),
        const SizedBox(height: 8),
        _MockInput(text: value),
      ],
    );
  }
}

class _MockChoice extends StatelessWidget {
  final String text;

  const _MockChoice({required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 46,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: FontMockupScreen._border),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontFamily: FontMockupScreen._bodyFont,
          fontSize: 14,
          fontWeight: FontWeight.w700,
          color: FontMockupScreen._textMain,
        ),
      ),
    );
  }
}

class _MockMbti extends StatelessWidget {
  final String text;

  const _MockMbti({required this.text});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        height: 44,
        margin: const EdgeInsets.only(right: 7),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: FontMockupScreen._surfaceSoft,
          borderRadius: BorderRadius.circular(15),
          border: Border.all(color: FontMockupScreen._border),
        ),
        child: _MockMbtiGlyph(text: text),
      ),
    );
  }
}

class _MockProfileCard extends StatelessWidget {
  final String name;
  final String percent;
  final Color color;
  final bool compact;

  const _MockProfileCard({
    required this.name,
    required this.percent,
    required this.color,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(compact ? 14 : 18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [color.withValues(alpha: 0.68), Colors.white],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.78)),
        boxShadow: [
          BoxShadow(
            color: color.withValues(alpha: 0.16),
            blurRadius: 22,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _MockPill(text: percent),
          const Spacer(),
          Text(
            name,
            style: TextStyle(
              fontFamily: FontMockupScreen._bodyFont,
              fontSize: compact ? 22 : 30,
              height: 1.1,
              fontWeight: FontWeight.w700,
              color: FontMockupScreen._textMain,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            compact ? '카페 · 산책' : '미디어커뮤니케이션학과 · ENFP',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontFamily: FontMockupScreen._bodyFont,
              fontSize: 13,
              fontWeight: FontWeight.w700,
              color: FontMockupScreen._textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class AccessScreen extends StatefulWidget {
  final String? message;

  const AccessScreen({super.key, this.message});

  @override
  State<AccessScreen> createState() => _AccessScreenState();
}

class _AccessScreenState extends State<AccessScreen> {
  final TextEditingController _codeController = TextEditingController();
  bool _isSubmitting = false;
  bool _isVerified = false;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    _codeController.addListener(_refreshCodeState);
  }

  void _refreshCodeState() {
    if (!mounted) return;
    setState(() => _errorText = null);
  }

  @override
  void dispose() {
    _codeController.removeListener(_refreshCodeState);
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _submitCode() async {
    if (_isSubmitting || _codeController.text.trim().isEmpty) return;
    HapticFeedback.selectionClick();
    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      await FestivalBackend.instance.redeemCode(_codeController.text);
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
        _isVerified = true;
      });
      await Future<void>.delayed(const Duration(milliseconds: 1050));
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(AppRoutes.start);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorText = error is FestivalBackendException
            ? error.message
            : '입장 코드 확인에 실패했어요.';
      });
    } finally {
      if (mounted && !_isVerified) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final canSubmit =
        _codeController.text.trim().isNotEmpty &&
        !_isSubmitting &&
        !_isVerified;

    return AppScaffold(
      showBack: false,
      backgroundColor: AppColors.desktopBackground,
      resizeToAvoidBottomInset: false,
      keyboardShiftFactor: 0.33,
      bottomBarKeyboardPaddingFactor: 0.33,
      child: Stack(
        children: [
          SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(22, 22, 22, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Image.asset(
                    'assets/images/mainlogo.png',
                    width: 118,
                    fit: BoxFit.contain,
                  ),
                ),
                const SizedBox(height: 26),
                const SizedBox(
                  width: double.infinity,
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '대동제에서 만나는 오늘의 인연!',
                      style: TextStyle(
                        fontSize: 34,
                        height: 1.18,
                        fontWeight: FontWeight.w900,
                        color: AppColors.textMain,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  '맞춤형 이상형 매칭 서비스 설레연입니다!',
                  style: TextStyle(
                    fontSize: 16,
                    height: 1.55,
                    color: AppColors.textSub,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (widget.message != null) ...[
                  const SizedBox(height: 16),
                  InfoBanner(
                    icon: CupertinoIcons.lock_shield,
                    text: widget.message!,
                    color: AppColors.primary,
                  ),
                ],
                const SizedBox(height: 26),
                SoftCard(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '아이폰 사용자의 경우, 아래 작업을 먼저 따라주세요!',
                        style: TextStyle(
                          fontSize: 18,
                          height: 1.32,
                          fontWeight: FontWeight.w900,
                          color: AppColors.textMain,
                        ),
                      ),
                      const SizedBox(height: 14),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(18),
                        child: AspectRatio(
                          aspectRatio: 860 / 1254,
                          child: Image.asset(
                            'assets/images/ios_home_add_guide.png',
                            width: double.infinity,
                            fit: BoxFit.cover,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                const Text(
                  '웹 앱에 접속해서 제공받은 6자리 코드를 입력해주세요.\n(안드로이드의 경우 삼성 인터넷, 크롬에서 바로 접속)',
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.45,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textSub,
                  ),
                ),
                const SizedBox(height: 12),
                SoftCard(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            CupertinoIcons.qrcode_viewfinder,
                            color: AppColors.primary,
                            size: 28,
                          ),
                          const SizedBox(width: 10),
                          const Expanded(
                            child: Text(
                              '1차 매칭권',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          StatusPill(text: '코드 확인', color: AppColors.mint),
                        ],
                      ),
                      const SizedBox(height: 18),
                      AppTextField(
                        controller: _codeController,
                        label: '입장 코드',
                        hintText: '',
                        textCapitalization: TextCapitalization.characters,
                        useMeongiFont: true,
                      ),
                      if (_errorText != null) ...[
                        const SizedBox(height: 10),
                        Text(
                          _errorText!,
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.35,
                            fontWeight: FontWeight.w700,
                            color: Color(0xFFDC2626),
                          ),
                        ),
                      ],
                      const SizedBox(height: 14),
                      const _TicketMetaRow(
                        icon: CupertinoIcons.clock,
                        label: '프로필 마감',
                        value: '19:30',
                      ),
                      const SizedBox(height: 10),
                      const _TicketMetaRow(
                        icon: CupertinoIcons.sparkles,
                        label: '결과 공개',
                        value: '20:00',
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                SoftCard(
                  color: AppColors.blush,
                  padding: const EdgeInsets.all(18),
                  child: Row(
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: AppColors.surface,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const Icon(
                          CupertinoIcons.bell_fill,
                          color: AppColors.primary,
                        ),
                      ),
                      const SizedBox(width: 12),
                      const Expanded(
                        child: Text(
                          '홈 화면에 추가하면 매칭 결과와 새 채팅 알림을 더 안정적으로 받을 수 있어요.',
                          style: TextStyle(
                            fontSize: 14,
                            height: 1.45,
                            color: AppColors.textMain,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          VerificationStatusOverlay(
            visible: _isSubmitting || _isVerified,
            completed: _isVerified,
          ),
        ],
      ),
      bottomBar: PrimaryButton(
        text: _isVerified ? '입장 완료' : (_isSubmitting ? '확인 중...' : '입장하기'),
        onPressed: canSubmit ? _submitCode : null,
      ),
    );
  }
}

class VerificationStatusOverlay extends StatelessWidget {
  final bool visible;
  final bool completed;

  const VerificationStatusOverlay({
    super.key,
    required this.visible,
    required this.completed,
  });

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        child: Container(
          width: double.infinity,
          height: double.infinity,
          color: visible ? AppColors.background : Colors.transparent,
          alignment: Alignment.center,
          padding: const EdgeInsets.all(26),
          child: AnimatedScale(
            scale: visible ? 1 : 0.96,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            child: SoftCard(
              padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 260),
                switchInCurve: Curves.easeOutBack,
                switchOutCurve: Curves.easeInCubic,
                child: completed
                    ? const VerificationStatusContent(
                        key: ValueKey('verified'),
                        completed: true,
                        title: '입장이 완료되었어요!',
                        subtitle: '이제 프로필을 작성하고 오늘의 인연을 준비해볼게요.',
                      )
                    : const VerificationStatusContent(
                        key: ValueKey('checking'),
                        completed: false,
                        title: '입장 코드 확인 중...',
                        subtitle: '매칭권을 확인하고 있어요. 잠시만 기다려주세요.',
                      ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class VerificationStatusContent extends StatelessWidget {
  final bool completed;
  final String title;
  final String subtitle;

  const VerificationStatusContent({
    super.key,
    required this.completed,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        FloatingStatusIcon(completed: completed),
        const SizedBox(height: 18),
        Text(
          title,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 23,
            height: 1.25,
            fontWeight: FontWeight.w900,
            color: AppColors.textMain,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          subtitle,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: 14,
            height: 1.5,
            fontWeight: FontWeight.w600,
            color: AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

class FloatingStatusIcon extends StatefulWidget {
  final bool completed;

  const FloatingStatusIcon({super.key, required this.completed});

  @override
  State<FloatingStatusIcon> createState() => _FloatingStatusIconState();
}

class _FloatingStatusIconState extends State<FloatingStatusIcon>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.completed) {
      return TweenAnimationBuilder<double>(
        tween: Tween(begin: 0.84, end: 1),
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOutBack,
        builder: (context, scale, child) {
          return Transform.scale(scale: scale, child: child);
        },
        child: Container(
          width: 76,
          height: 76,
          decoration: BoxDecoration(
            color: AppColors.mint.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: const Icon(
            CupertinoIcons.checkmark_seal_fill,
            color: AppColors.mint,
            size: 42,
          ),
        ),
      );
    }

    return SizedBox(
      width: 96,
      height: 42,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final visibleCount = (_controller.value * 4).floor().clamp(1, 3);
          return Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: List.generate(3, (index) {
              final isVisible = index < visibleCount;
              return AnimatedOpacity(
                opacity: isVisible ? 1 : 0,
                duration: const Duration(milliseconds: 120),
                curve: Curves.easeOutCubic,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Image.asset(
                    'assets/images/loading_clay_dot.png',
                    width: 24,
                    height: 24,
                    fit: BoxFit.contain,
                  ),
                ),
              );
            }),
          );
        },
      ),
    );
  }
}

class RedeemScreen extends StatefulWidget {
  final String token;

  const RedeemScreen({super.key, required this.token});

  @override
  State<RedeemScreen> createState() => _RedeemScreenState();
}

class _RedeemScreenState extends State<RedeemScreen> {
  String? _errorText;
  bool _isVerified = false;

  @override
  void initState() {
    super.initState();
    unawaited(_redeem());
  }

  Future<void> _redeem() async {
    try {
      await FestivalBackend.instance.redeemQrToken(widget.token);
      if (!mounted) return;
      setState(() => _isVerified = true);
      await Future<void>.delayed(const Duration(milliseconds: 1050));
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(AppRoutes.start);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorText = error is FestivalBackendException
            ? error.message
            : 'QR 인증에 실패했어요.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final errorText = _errorText;
    return AppScaffold(
      showBack: false,
      backgroundColor: AppColors.desktopBackground,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: SoftCard(
            padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Image.asset(
                  'assets/images/mainlogo.png',
                  width: 86,
                  fit: BoxFit.contain,
                ),
                const SizedBox(height: 18),
                if (errorText == null)
                  VerificationStatusContent(
                    completed: _isVerified,
                    title: _isVerified ? '입장이 완료되었어요!' : '매칭권 확인 중...',
                    subtitle: _isVerified
                        ? '이제 프로필을 작성하고 오늘의 인연을 준비해볼게요.'
                        : 'QR로 연결된 매칭권을 확인하고 있어요.',
                  )
                else ...[
                  const Icon(
                    CupertinoIcons.exclamationmark_triangle,
                    color: Color(0xFFDC2626),
                    size: 34,
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    'QR 인증 실패',
                    style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    errorText,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 14,
                      height: 1.55,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textSub,
                    ),
                  ),
                  const SizedBox(height: 18),
                  PrimaryButton(
                    text: '코드 직접 입력하기',
                    onPressed: () => Navigator.of(
                      context,
                    ).pushReplacementNamed(AppRoutes.access),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TicketMetaRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _TicketMetaRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 18, color: AppColors.textSub),
        const SizedBox(width: 8),
        Text(
          label,
          style: const TextStyle(
            fontSize: 14,
            color: AppColors.textSub,
            fontWeight: FontWeight.w600,
          ),
        ),
        const Spacer(),
        Text(
          value,
          style: const TextStyle(
            fontSize: 14,
            color: AppColors.textMain,
            fontWeight: FontWeight.w800,
          ),
        ),
      ],
    );
  }
}

class SignupScreen extends StatefulWidget {
  const SignupScreen({super.key});

  @override
  State<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends State<SignupScreen>
    with WidgetsBindingObserver {
  final _nickname = TextEditingController();
  final _department = TextEditingController();
  final _intro = TextEditingController();
  final _introFocusNode = FocusNode();
  final ImagePicker _imagePicker = ImagePicker();
  final FestivalAvatarGenerationClient _avatarClient =
      FestivalAvatarGenerationClient();

  Timer? _draftDebounce;
  String _gender = '';
  int _age = 22;
  bool _isPickingPhoto = false;
  bool _isUploadingPhoto = false;
  bool _isGeneratingAvatar = false;
  bool _isApprovingAvatar = false;
  bool _avatarSourceLocked = false;
  bool _isLoadingDraft = true;
  XFile? _profilePhoto;
  Uint8List? _profilePhotoBytes;
  String? _activeAvatarJobId;
  String? _activeAvatarSourcePhotoId;
  int? _activeAvatarSourceSelectionVersion;
  List<AvatarCandidate> _avatarCandidates = const [];
  String? _restoredPhotoUrl;
  String? _restoredPhotoContentType;
  String? _restoredPhotoOriginalName;
  int? _restoredPhotoSizeBytes;
  String? _studentAffiliation;
  final List<String> _mbti = ['E', 'N', 'F', 'P'];
  bool _isSavingProfile = false;
  bool _isSyncingPush = false;
  bool _notificationReady = false;
  String? _lastSavedDraftSignature;
  FestivalEventSchedule? _eventSchedule;
  StreamSubscription<FestivalEventSchedule?>? _scheduleSubscription;

  bool get _isProfileTasteLocked =>
      _eventSchedule?.isProfileTasteLocked() ?? false;

  bool get _hasApprovedAvatar => _restoredPhotoUrl?.trim().isNotEmpty == true;

  bool get _hasActiveAvatarSource =>
      _activeAvatarSourcePhotoId?.trim().isNotEmpty == true ||
      _activeAvatarSourceSelectionVersion != null;

  bool get _isAvatarBusy =>
      _isUploadingPhoto || _isGeneratingAvatar || _isApprovingAvatar;

  bool get _canStartAvatarGeneration =>
      _profilePhoto != null &&
      _profilePhotoBytes != null &&
      !_avatarSourceLocked &&
      !_hasApprovedAvatar &&
      !_isAvatarBusy;

  bool get _hasRequiredProfileFields {
    return _nickname.text.trim().isNotEmpty &&
        _gender.isNotEmpty &&
        _department.text.trim().isNotEmpty &&
        _studentAffiliation != null &&
        _age >= 19 &&
        _mbti.length == 4 &&
        _mbti.every((letter) => letter.isNotEmpty) &&
        _notificationReady;
  }

  bool get _canStartAvatarFlow =>
      _hasRequiredProfileFields && _canStartAvatarGeneration;

  bool get _canGoNext => _hasRequiredProfileFields && _hasApprovedAvatar;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _nickname.addListener(_handleDraftFieldChanged);
    _department.addListener(_handleDraftFieldChanged);
    _intro.addListener(_handleDraftFieldChanged);
    _introFocusNode.addListener(_handleIntroFocusChanged);
    unawaited(_loadProfileDraft());
    unawaited(_loadNotificationState());
    _scheduleSubscription = FestivalBackend.instance
        .watchEventSchedule()
        .listen((schedule) {
          if (!mounted) return;
          setState(() => _eventSchedule = schedule);
        });
  }

  void _handleIntroFocusChanged() {
    if (!mounted) return;
    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _draftDebounce?.cancel();
      unawaited(_saveProfileDraft(force: true));
    }
  }

  void _handleDraftFieldChanged() {
    if (!mounted) return;
    setState(() {});
    _scheduleDraftSave();
  }

  Future<void> _loadProfileDraft() async {
    try {
      final draft = await FestivalBackend.instance.loadProfileDraft();
      if (!mounted) return;

      if (draft != null) {
        _nickname.text = draft.nickname;
        _department.text = draft.department;
        _intro.text = draft.intro;
        _gender = draft.gender;
        _age = draft.age;
        _studentAffiliation = draft.studentAffiliation;
        _mbti
          ..clear()
          ..addAll(draft.mbti.characters.take(4));
        while (_mbti.length < 4) {
          _mbti.add(['E', 'N', 'F', 'P'][_mbti.length]);
        }
        _restoredPhotoUrl = draft.photoUrl;
        _restoredPhotoContentType = draft.photoContentType;
        _restoredPhotoOriginalName = draft.photoOriginalName;
        _restoredPhotoSizeBytes = draft.photoSizeBytes;
      }

      setState(() {
        _isLoadingDraft = false;
        _lastSavedDraftSignature = _draftSignature();
      });

      if (draft != null && _draftHasContent(draft)) {
        showAppSnack(context, '작성 중이던 프로필을 불러왔어요.');
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _isLoadingDraft = false);
      showAppSnack(context, '작성 중이던 내용을 불러오지 못했어요.');
    }
  }

  bool _draftHasContent(ProfileDraft draft) {
    return draft.nickname.trim().isNotEmpty ||
        draft.department.trim().isNotEmpty ||
        draft.studentAffiliation != null ||
        draft.intro.trim().isNotEmpty ||
        draft.hasPhoto;
  }

  void _scheduleDraftSave() {
    if (_isLoadingDraft || _isSavingProfile) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 450), () {
      unawaited(_saveProfileDraft());
    });
  }

  Future<void> _saveProfileDraft({bool force = false}) async {
    if (_isLoadingDraft || _isSavingProfile) return;

    final signature = _draftSignature();
    if (!force && signature == _lastSavedDraftSignature) return;

    try {
      await FestivalBackend.instance.saveProfileDraft(_profileDraftData());
      _lastSavedDraftSignature = signature;
    } catch (_) {
      // Draft saving is best-effort so typing never gets blocked by network.
    }
  }

  String _draftSignature() => jsonEncode(_profileDraftData());

  Map<String, Object?> _profileDraftData() {
    final photoUrl = _restoredPhotoUrl;
    return {
      'nickname': _nickname.text.trim(),
      'gender': _gender,
      'department': _department.text.trim(),
      'studentAffiliation': _studentAffiliation,
      'age': _age,
      'mbti': _mbti.join(),
      'hasPhoto': photoUrl?.trim().isNotEmpty == true,
      'photoMode': photoUrl?.trim().isNotEmpty == true ? 'avatar' : null,
      'photoUrl': photoUrl,
      'photoStoragePath': null,
      'photoContentType': _restoredPhotoContentType,
      'photoOriginalName': _restoredPhotoOriginalName,
      'photoSizeBytes': _restoredPhotoSizeBytes,
      'avatar': photoUrl?.trim().isNotEmpty == true
          ? {'status': 'approved', 'approvedAvatarUrl': photoUrl}
          : null,
      'intro': _intro.text.trim(),
    };
  }

  void _updateDraftField(VoidCallback update) {
    setState(update);
    _scheduleDraftSave();
  }

  Future<void> _loadNotificationState() async {
    final status = await FestivalPushService.instance
        .currentAuthorizationStatus();
    if (!mounted) return;
    final ready =
        status == AuthorizationStatus.authorized ||
        status == AuthorizationStatus.provisional;
    setState(() => _notificationReady = ready);
    if (ready) {
      final result = await FestivalPushService.instance
          .syncTokenSafelyDetailed();
      if (mounted && !result.success) {
        debugPrint(
          '[FESTIVAL_PUSH] signup auto sync failed: ${result.debugMessage}',
        );
        setState(() => _notificationReady = false);
      }
    }
  }

  Future<void> _enableNotifications() async {
    if (_isSyncingPush) return;
    HapticFeedback.selectionClick();

    final hint = FestivalPushService.instance.iosHomeScreenHint;
    if (hint != null) {
      showAppSnack(context, hint);
      return;
    }

    setState(() => _isSyncingPush = true);
    final result = await FestivalPushService.instance
        .requestPermissionAndSyncDetailed();
    if (!mounted) return;
    setState(() {
      _isSyncingPush = false;
      _notificationReady = result.success;
    });
    showAppSnack(context, result.debugMessage);
  }

  Future<void> _pickProfilePhoto() async {
    if (_isPickingPhoto || _isSavingProfile || _isAvatarBusy) return;
    if (_avatarSourceLocked || _hasApprovedAvatar) {
      showAppSnack(context, avatarSourceLockedMessage);
      return;
    }

    HapticFeedback.selectionClick();
    setState(() => _isPickingPhoto = true);

    try {
      final pickedPhoto = await _imagePicker.pickImage(
        source: ImageSource.gallery,
      );
      if (pickedPhoto == null) return;

      final bytes = await pickedPhoto.readAsBytes();
      if (bytes.isEmpty) {
        if (!mounted) return;
        showAppSnack(context, '사진 파일을 다시 선택해주세요.');
        return;
      }
      if (bytes.length > 10 * 1024 * 1024) {
        if (!mounted) return;
        showAppSnack(context, '이미지는 10MB 이하로 올려주세요.');
        return;
      }

      final contentType = _avatarContentTypeForFileName(
        pickedPhoto.name,
        pickedPhoto.mimeType,
      );

      if (!mounted) return;
      setState(() {
        _profilePhoto = pickedPhoto;
        _profilePhotoBytes = bytes;
        _restoredPhotoUrl = null;
        _restoredPhotoContentType = contentType;
        _restoredPhotoOriginalName = pickedPhoto.name;
        _restoredPhotoSizeBytes = bytes.length;
        _activeAvatarJobId = null;
        _activeAvatarSourcePhotoId = null;
        _activeAvatarSourceSelectionVersion = null;
        _avatarCandidates = const [];
      });

      await _saveProfileDraft(force: true);
    } catch (_) {
      if (!mounted) return;
      showAppSnack(context, '사진 선택에 실패했어요. 다시 선택해주세요.');
    } finally {
      if (mounted) {
        setState(() => _isPickingPhoto = false);
      }
    }
  }

  Future<void> _removeProfilePhoto() async {
    if (_avatarSourceLocked || _hasApprovedAvatar || _isAvatarBusy) {
      showAppSnack(context, avatarSourceLockedMessage);
      return;
    }

    HapticFeedback.selectionClick();
    setState(() {
      _profilePhoto = null;
      _profilePhotoBytes = null;
      _restoredPhotoUrl = null;
      _restoredPhotoContentType = null;
      _restoredPhotoOriginalName = null;
      _restoredPhotoSizeBytes = null;
      _activeAvatarJobId = null;
      _activeAvatarSourcePhotoId = null;
      _activeAvatarSourceSelectionVersion = null;
      _avatarCandidates = const [];
    });
    await _saveProfileDraft(force: true);
  }

  Future<void> _continueToTaste() async {
    if (_isSavingProfile || _isProfileTasteLocked) return;
    if (_hasApprovedAvatar && _canGoNext) {
      await _saveApprovedAvatarProfileAndContinue();
      return;
    }
    if (_canStartAvatarFlow) {
      await _startAvatarGeneration();
      return;
    }
    showAppSnack(context, '프로필 정보와 알림 설정, 아바타로 만들 사진을 확인해주세요.');
  }

  Future<void> _startAvatarGeneration() async {
    final photo = _profilePhoto;
    final bytes = _profilePhotoBytes;
    if (photo == null || bytes == null) {
      showAppSnack(context, '아바타로 만들 사진을 먼저 선택해주세요.');
      return;
    }

    HapticFeedback.selectionClick();
    _draftDebounce?.cancel();
    setState(() {
      _avatarSourceLocked = true;
      _isUploadingPhoto = true;
      _avatarCandidates = const [];
    });

    try {
      final upload = await _avatarClient.uploadAvatarSourcePhoto(
        bytes: bytes,
        fileName: photo.name,
        contentType:
            _restoredPhotoContentType ??
            _avatarContentTypeForFileName(photo.name, photo.mimeType),
      );
      if (!mounted) return;

      final jobId = upload.jobId;
      setState(() {
        _activeAvatarJobId = jobId;
        _activeAvatarSourcePhotoId = upload.photoId;
        _activeAvatarSourceSelectionVersion = upload.sourceSelectionVersion;
        _isUploadingPhoto = false;
        _isGeneratingAvatar = true;
      });

      final result = await _avatarClient.pollUntilPreviewReady(
        jobId,
        shouldContinue: () => mounted && _activeAvatarJobId == jobId,
      );
      if (!mounted || _activeAvatarJobId != jobId) return;

      setState(() {
        _isGeneratingAvatar = false;
        _avatarCandidates = result.candidates;
      });

      if (result.status == AvatarJobStatus.previewReady &&
          _avatarCandidates.isNotEmpty) {
        await _showAvatarCandidatesDialog(_avatarCandidates);
        return;
      }

      showAppSnack(context, _messageForAvatarStatus(result.status));
    } on AvatarGenerationClientException catch (error) {
      if (!mounted) return;
      setState(() {
        _isUploadingPhoto = false;
        _isGeneratingAvatar = false;
        if (error.code == 'avatar_already_approved') {
          _avatarSourceLocked = true;
        }
      });
      showAppSnack(context, error.userMessage);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isUploadingPhoto = false;
        _isGeneratingAvatar = false;
      });
      showAppSnack(context, avatarGenericFailureMessage);
    }
  }

  String _messageForAvatarStatus(AvatarJobStatus status) {
    switch (status) {
      case AvatarJobStatus.noPreviewableCandidates:
      case AvatarJobStatus.needsReview:
        return avatarNoPreviewableMessage;
      case AvatarJobStatus.superseded:
      case AvatarJobStatus.cancelled:
        return avatarSourceLockedMessage;
      case AvatarJobStatus.approved:
        return avatarAlreadyApprovedMessage;
      case AvatarJobStatus.failed:
      case AvatarJobStatus.queued:
      case AvatarJobStatus.running:
      case AvatarJobStatus.qaPending:
      case AvatarJobStatus.previewReady:
      case AvatarJobStatus.unknown:
        return avatarGenericFailureMessage;
    }
  }

  Future<void> _showAvatarCandidatesDialog(
    List<AvatarCandidate> candidates,
  ) async {
    if (candidates.isEmpty || !mounted) return;

    final approved = await showDialog<AvatarApprovalResult>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        var dialogApproving = false;
        return StatefulBuilder(
          builder: (context, setDialogState) {
            void approve(String candidateId) {
              if (dialogApproving) return;
              setDialogState(() => dialogApproving = true);
              if (mounted) {
                setState(() => _isApprovingAvatar = true);
              }
              unawaited(() async {
                try {
                  final result = await _avatarClient.approveAvatarCandidate(
                    candidateId,
                  );
                  if (!mounted) return;
                  if (!dialogContext.mounted) return;
                  Navigator.of(dialogContext).pop(result);
                } on AvatarGenerationClientException catch (error) {
                  if (!mounted) return;
                  setState(() => _isApprovingAvatar = false);
                  setDialogState(() => dialogApproving = false);
                  _showAvatarError(error.userMessage);
                } catch (_) {
                  if (!mounted) return;
                  setState(() => _isApprovingAvatar = false);
                  setDialogState(() => dialogApproving = false);
                  _showAvatarError(avatarGenericFailureMessage);
                }
              }());
            }

            return AvatarCandidateSelectionDialog(
              candidates: candidates,
              approving: dialogApproving,
              onApprove: approve,
            );
          },
        );
      },
    );

    if (approved != null) {
      await _completeApprovedAvatar(approved);
    } else if (mounted) {
      setState(() => _isApprovingAvatar = false);
    }
  }

  void _showAvatarError(String message) {
    if (!mounted) return;
    showAppSnack(context, message);
  }

  Future<void> _completeApprovedAvatar(AvatarApprovalResult approved) async {
    if (!mounted) return;
    setState(() {
      _restoredPhotoUrl = approved.approvedAvatarUrl;
      _avatarSourceLocked = true;
      _isApprovingAvatar = false;
      _isGeneratingAvatar = false;
      _isUploadingPhoto = false;
    });
    await _saveProfileDraft(force: true);
    await _saveApprovedAvatarProfileAndContinue();
  }

  Future<void> _saveApprovedAvatarProfileAndContinue() async {
    final approvedAvatarUrl = _restoredPhotoUrl?.trim() ?? '';
    if (approvedAvatarUrl.isEmpty) {
      showAppSnack(context, '프로필에 사용할 아바타를 먼저 선택해주세요.');
      return;
    }
    if (_isSavingProfile) return;

    HapticFeedback.selectionClick();
    setState(() => _isSavingProfile = true);

    try {
      _draftDebounce?.cancel();
      await FestivalBackend.instance.saveProfile({
        'nickname': _nickname.text.trim(),
        'gender': _gender,
        'department': _department.text.trim(),
        'studentAffiliation': _studentAffiliation,
        'age': _age,
        'mbti': _mbti.join(),
        'hasPhoto': true,
        'photoMode': 'avatar',
        'photoUrl': approvedAvatarUrl,
        'photoStoragePath': null,
        'photoContentType': _restoredPhotoContentType,
        'photoOriginalName': _restoredPhotoOriginalName,
        'photoSizeBytes': _restoredPhotoSizeBytes,
        'avatar': {
          'status': 'approved',
          'approvedAvatarUrl': approvedAvatarUrl,
        },
        'intro': _intro.text.trim(),
      });

      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed(
        AppRoutes.taste,
        arguments: const TasteTrainingResume(nextIndex: 0, likedCount: 0),
      );
    } catch (error) {
      if (!mounted) return;
      showAppSnack(
        context,
        error is FestivalBackendException ? error.message : '프로필 저장에 실패했어요.',
      );
    } finally {
      if (mounted) {
        setState(() => _isSavingProfile = false);
      }
    }
  }

  @override
  void dispose() {
    _draftDebounce?.cancel();
    if (!_isSavingProfile) {
      unawaited(_saveProfileDraft(force: true));
    }
    _nickname.removeListener(_handleDraftFieldChanged);
    _department.removeListener(_handleDraftFieldChanged);
    _intro.removeListener(_handleDraftFieldChanged);
    _introFocusNode.removeListener(_handleIntroFocusChanged);
    _scheduleSubscription?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    _nickname.dispose();
    _department.dispose();
    _intro.dispose();
    _introFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoadingDraft) {
      return const AppScaffold(
        title: '프로필 작성',
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: SoftCard(
              padding: EdgeInsets.fromLTRB(22, 24, 22, 22),
              child: VerificationStatusContent(
                completed: false,
                title: '작성 내용 확인 중...',
                subtitle: '이전에 입력하던 프로필이 있는지 확인하고 있어요.',
              ),
            ),
          ),
        ),
      );
    }

    return AppScaffold(
      title: '프로필 작성',
      resizeToAvoidBottomInset: false,
      keyboardResizeFactor: _introFocusNode.hasFocus ? 0.33 : 0,
      bottomBarKeyboardPaddingFactor: _introFocusNode.hasFocus ? 0.33 : 0,
      child: Stack(
        children: [
          SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const StepHeader(
                  current: 1,
                  total: 2,
                  title: '매칭에 필요한 정보만 받을게요',
                  subtitle: '축제 종료 후 별도 보관 정책에 따라 정리되는 일회성 프로필이에요.',
                ),
                if (_isProfileTasteLocked) ...[
                  const SizedBox(height: 16),
                  SoftCard(
                    color: AppColors.blush,
                    padding: const EdgeInsets.all(16),
                    child: Text(
                      '프로필 작성이 ${_eventSchedule!.formatClockKst(_eventSchedule!.profileTasteLockAt)}에 마감되었어요.',
                      style: const TextStyle(
                        fontSize: 14,
                        height: 1.4,
                        fontWeight: FontWeight.w800,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                AppTextField(
                  controller: _nickname,
                  label: '닉네임',
                  hintText: '친구들이 부르는 이름',
                ),
                const SizedBox(height: 16),
                FieldLabel(
                  text: '성별',
                  child: SegmentedOptions(
                    values: const ['남성', '여성'],
                    selected: _gender,
                    onSelected: (value) {
                      if (_gender == value) return;
                      _updateDraftField(() => _gender = value);
                    },
                  ),
                ),
                const SizedBox(height: 16),
                AppTextField(
                  controller: _department,
                  label: '학과',
                  hintText: '예: 경영학과',
                ),
                const SizedBox(height: 16),
                FieldLabel(
                  text: '소속',
                  child: StudentAffiliationOptions(
                    selected: _studentAffiliation,
                    onSelected: (value) {
                      if (_studentAffiliation == value) return;
                      HapticFeedback.selectionClick();
                      _updateDraftField(() => _studentAffiliation = value);
                    },
                  ),
                ),
                const SizedBox(height: 16),
                FieldLabel(
                  text: '나이',
                  child: SoftCard(
                    padding: const EdgeInsets.fromLTRB(18, 12, 18, 12),
                    child: Column(
                      children: [
                        Row(
                          children: [
                            const Text(
                              '연나이',
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                color: AppColors.textSub,
                              ),
                            ),
                            const Spacer(),
                            Text(
                              '$_age세',
                              style: const TextStyle(
                                fontSize: 22,
                                fontWeight: FontWeight.w900,
                                color: AppColors.primary,
                              ),
                            ),
                          ],
                        ),
                        SliderTheme(
                          data: SliderTheme.of(context).copyWith(
                            trackHeight: 4,
                            activeTrackColor: AppColors.primary,
                            inactiveTrackColor: AppColors.border,
                            activeTickMarkColor: Colors.transparent,
                            inactiveTickMarkColor: Colors.transparent,
                            tickMarkShape: SliderTickMarkShape.noTickMark,
                            thumbColor: AppColors.primary,
                            overlayColor: AppColors.primary.withValues(
                              alpha: 0.12,
                            ),
                          ),
                          child: Slider(
                            value: _age.toDouble(),
                            min: 19,
                            max: 29,
                            divisions: 10,
                            onChanged: (value) => _updateDraftField(() {
                              _age = value.round();
                            }),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                FieldLabel(
                  text: 'MBTI',
                  child: SoftCard(
                    color: AppColors.input,
                    padding: const EdgeInsets.all(6),
                    radius: 18,
                    child: Row(
                      children: [
                        Expanded(
                          child: MbtiAxisSelector(
                            top: 'E',
                            bottom: 'I',
                            selected: _mbti[0],
                            onChanged: (value) {
                              if (_mbti[0] == value) return;
                              _updateDraftField(() => _mbti[0] = value);
                            },
                          ),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: MbtiAxisSelector(
                            top: 'N',
                            bottom: 'S',
                            selected: _mbti[1],
                            onChanged: (value) {
                              if (_mbti[1] == value) return;
                              _updateDraftField(() => _mbti[1] = value);
                            },
                          ),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: MbtiAxisSelector(
                            top: 'F',
                            bottom: 'T',
                            selected: _mbti[2],
                            onChanged: (value) {
                              if (_mbti[2] == value) return;
                              _updateDraftField(() => _mbti[2] = value);
                            },
                          ),
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: MbtiAxisSelector(
                            top: 'J',
                            bottom: 'P',
                            selected: _mbti[3],
                            onChanged: (value) {
                              if (_mbti[3] == value) return;
                              _updateDraftField(() => _mbti[3] = value);
                            },
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                FieldLabel(
                  text: '사진',
                  child: AvatarPhotoInput(
                    hasLocalPhoto:
                        _profilePhotoBytes != null || _hasApprovedAvatar,
                    sourceLocked:
                        _avatarSourceLocked ||
                        _hasActiveAvatarSource ||
                        _isGeneratingAvatar,
                    approvedAvatarUrl: _restoredPhotoUrl ?? '',
                    isBusy: _isPickingPhoto || _isAvatarBusy,
                    fileName:
                        _profilePhoto?.name ??
                        _restoredPhotoOriginalName ??
                        '선택한 사진',
                    localPreviewBytes: _profilePhotoBytes,
                    onPick: _pickProfilePhoto,
                    onRemove: _removeProfilePhoto,
                  ),
                ),
                const SizedBox(height: 16),
                AppTextField(
                  controller: _intro,
                  focusNode: _introFocusNode,
                  label: '자기소개',
                  hintText: '',
                  minLines: 4,
                  maxLines: 5,
                  scrollPadding: const EdgeInsets.only(bottom: 180),
                ),
                const SizedBox(height: 12),
                InfoBanner(
                  icon: _notificationReady
                      ? CupertinoIcons.bell_fill
                      : CupertinoIcons.bell,
                  text: _notificationReady
                      ? '새 채팅 알림을 받을 준비가 됐어요.'
                      : '새 채팅 알림을 받으려면 알림을 켜주세요.',
                  color: _notificationReady
                      ? AppColors.mint
                      : AppColors.primary,
                  actionText: _notificationReady
                      ? null
                      : (_isSyncingPush ? '확인 중' : '알림 켜기'),
                  onAction: _isSyncingPush ? null : _enableNotifications,
                ),
                const SizedBox(height: 12),
                const InfoBanner(
                  icon: CupertinoIcons.timer,
                  text: '19:30 이후에는 1차 추천 계산을 위해 프로필 수정이 잠시 잠겨요.',
                  color: AppColors.blue,
                ),
              ],
            ),
          ),
          if (_isUploadingPhoto || _isGeneratingAvatar)
            const Positioned.fill(child: AvatarGeneratingOverlay()),
        ],
      ),
      bottomBar: PrimaryButton(
        text: _isGeneratingAvatar || _isUploadingPhoto
            ? '아바타 생성중...'
            : (_isApprovingAvatar || _isSavingProfile
                  ? '저장하는 중...'
                  : (_hasApprovedAvatar ? '다음' : '아바타 만들기')),
        onPressed:
            !_isProfileTasteLocked &&
                !_isSavingProfile &&
                !_isAvatarBusy &&
                (_canGoNext || _canStartAvatarFlow)
            ? _continueToTaste
            : null,
      ),
    );
  }
}

class StudentAffiliationOptions extends StatelessWidget {
  final String? selected;
  final ValueChanged<String> onSelected;

  const StudentAffiliationOptions({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _StudentAffiliationOption(
            text: '연세대 학생이에요',
            selected: selected == 'yonsei',
            onTap: () => onSelected('yonsei'),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _StudentAffiliationOption(
            text: '타 대학 학생이에요',
            selected: selected == 'other',
            onTap: () => onSelected('other'),
          ),
        ),
      ],
    );
  }
}

class _StudentAffiliationOption extends StatelessWidget {
  final String text;
  final bool selected;
  final VoidCallback onTap;

  const _StudentAffiliationOption({
    required this.text,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: 44,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: selected ? AppColors.blush : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected
                ? AppColors.primary.withValues(alpha: 0.30)
                : AppColors.border,
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 20,
              height: 20,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: selected ? AppColors.primary : AppColors.surface,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(
                  color: selected ? AppColors.primary : AppColors.border,
                ),
              ),
              child: selected
                  ? const Icon(
                      CupertinoIcons.checkmark_alt,
                      size: 14,
                      color: Colors.white,
                    )
                  : null,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w800,
                  color: selected ? AppColors.primary : AppColors.textMain,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class TasteTrainingScreen extends StatefulWidget {
  final TasteTrainingResume? resume;

  const TasteTrainingScreen({super.key, this.resume});

  @override
  State<TasteTrainingScreen> createState() => _TasteTrainingScreenState();
}

class _TasteTrainingScreenState extends State<TasteTrainingScreen>
    with TickerProviderStateMixin {
  int _index = 0;
  int _liked = 0;
  Offset _dragOffset = Offset.zero;
  bool _isAnimating = false;
  bool _pendingLiked = false;
  bool _isTrainingCompleted = false;
  bool _isResumeLoading = false;
  bool _isKillingSession = false;
  double _revealProgress = 1;
  String? _resumeError;
  List<TasteCardData> _cards = const [];

  late final AnimationController _flyController;
  late final AnimationController _snapController;
  late final AnimationController _revealController;
  Animation<Offset>? _flyAnimation;
  Animation<Offset>? _snapAnimation;

  @override
  void initState() {
    super.initState();
    _flyController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 320),
          )
          ..addListener(_syncFlyAnimation)
          ..addStatusListener(_handleFlyStatus);
    _snapController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 360),
          )
          ..addListener(_syncSnapAnimation)
          ..addStatusListener(_handleSnapStatus);
    _revealController =
        AnimationController(
            vsync: this,
            duration: const Duration(milliseconds: 220),
            value: 1,
          )
          ..addListener(_syncRevealAnimation)
          ..addStatusListener(_handleRevealStatus);

    _isResumeLoading = true;
    unawaited(_loadTasteCardsAndProgress(widget.resume));
  }

  @override
  void dispose() {
    _flyController
      ..removeListener(_syncFlyAnimation)
      ..removeStatusListener(_handleFlyStatus)
      ..dispose();
    _snapController
      ..removeListener(_syncSnapAnimation)
      ..removeStatusListener(_handleSnapStatus)
      ..dispose();
    _revealController
      ..removeListener(_syncRevealAnimation)
      ..removeStatusListener(_handleRevealStatus)
      ..dispose();
    super.dispose();
  }

  void _syncFlyAnimation() {
    final animation = _flyAnimation;
    if (!mounted || animation == null) return;
    setState(() => _dragOffset = animation.value);
  }

  void _syncSnapAnimation() {
    final animation = _snapAnimation;
    if (!mounted || animation == null) return;
    setState(() => _dragOffset = animation.value);
  }

  void _syncRevealAnimation() {
    if (!mounted) return;
    setState(() => _revealProgress = _revealController.value);
  }

  void _handleFlyStatus(AnimationStatus status) {
    if (status == AnimationStatus.completed) {
      _commitAnswer(_pendingLiked);
    }
  }

  void _handleSnapStatus(AnimationStatus status) {
    if (status == AnimationStatus.completed && mounted) {
      setState(() {
        _dragOffset = Offset.zero;
        _isAnimating = false;
        _snapAnimation = null;
      });
    }
  }

  void _handleRevealStatus(AnimationStatus status) {
    if (status == AnimationStatus.completed && mounted) {
      setState(() {
        _revealProgress = 1;
      });
    }
  }

  void _applyTasteResume(TasteTrainingResume resume) {
    if (_cards.isEmpty) return;
    final nextIndex = resume.nextIndex;
    if (nextIndex >= _cards.length) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Navigator.of(
          context,
        ).pushNamedAndRemoveUntil(AppRoutes.waiting, (route) => false);
      });
      return;
    }

    _index = nextIndex.clamp(0, _cards.length - 1).toInt();
    _liked = resume.likedCount.clamp(0, _cards.length).toInt();
  }

  Future<void> _loadTasteCardsAndProgress(TasteTrainingResume? resume) async {
    try {
      final cards = await FestivalBackend.instance.loadTasteCards();
      if (!mounted) return;
      setState(() {
        _cards = cards;
        _resumeError = null;
      });

      if (resume == null) {
        await _loadSavedTasteProgress();
      } else {
        if (!mounted) return;
        setState(() {
          _applyTasteResume(resume);
          _isResumeLoading = false;
        });
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isResumeLoading = false;
        _resumeError = error is FestivalBackendException
            ? error.message
            : 'AI 프로필 사진을 불러오지 못했어요.';
      });
    }
  }

  Future<void> _loadSavedTasteProgress() async {
    try {
      final progress = await FestivalBackend.instance.loadOnboardingProgress();
      if (!mounted) return;

      switch (progress.nextStep) {
        case FestivalNextStep.profile:
          Navigator.of(context).pushReplacementNamed(AppRoutes.signup);
        case FestivalNextStep.taste:
          setState(() {
            _applyTasteResume(progress.tasteResume);
            _isResumeLoading = false;
            _resumeError = null;
          });
        case FestivalNextStep.waiting:
          final route = await FestivalBackend.instance.matchesOrWaitingRoute();
          if (!mounted) return;
          Navigator.of(
            context,
          ).pushNamedAndRemoveUntil(route, (route) => false);
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _isResumeLoading = false;
        _resumeError = error is FestivalBackendException
            ? error.message
            : '취향 학습 진행 상태를 불러오지 못했어요.';
      });
    }
  }

  void _retryLoadSavedTasteProgress() {
    if (_isResumeLoading) return;
    setState(() {
      _isResumeLoading = true;
      _resumeError = null;
    });
    unawaited(_loadTasteCardsAndProgress(widget.resume));
  }

  Future<void> _killSession() async {
    if (_isKillingSession) return;
    setState(() => _isKillingSession = true);
    try {
      await FestivalBackend.instance.logout();
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(AppRoutes.access, (route) => false);
    } catch (_) {
      if (!mounted) return;
      showAppSnack(context, '세션 초기화에 실패했어요. 잠시 후 다시 시도해주세요.');
      setState(() => _isKillingSession = false);
    }
  }

  void _commitAnswer(bool liked) {
    final currentCard = _cards[_index];
    final nextLikedCount = _liked + (liked ? 1 : 0);
    _runSilently(
      FestivalBackend.instance.recordTasteSwipe(
        index: _index,
        card: currentCard,
        liked: liked,
      ),
    );

    if (_index >= _cards.length - 1) {
      _runSilently(
        FestivalBackend.instance.completeTasteTraining(
          likedCount: nextLikedCount,
          total: _cards.length,
        ),
      );
      setState(() {
        _liked = nextLikedCount;
        _dragOffset = Offset.zero;
        _flyAnimation = null;
        _isAnimating = false;
        _isTrainingCompleted = true;
      });
      unawaited(_finishTasteTraining());
      return;
    }
    setState(() {
      _liked = nextLikedCount;
      _index += 1;
      _dragOffset = Offset.zero;
      _flyAnimation = null;
      _revealProgress = 0;
    });
    _revealController.forward(from: 0);
    _isAnimating = false;
  }

  Future<void> _finishTasteTraining() async {
    await Future<void>.delayed(const Duration(milliseconds: 1050));
    if (!mounted) return;
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(AppRoutes.waiting, (route) => false);
  }

  void _programmaticSwipe(bool liked) {
    if (_isAnimating || _isTrainingCompleted) return;
    HapticFeedback.mediumImpact();
    _flyOff(liked, from: Offset(liked ? 18 : -18, 0));
  }

  void _flyOff(bool liked, {Offset? from}) {
    if (_isTrainingCompleted || (_isAnimating && from == null)) return;
    final width = MediaQuery.of(context).size.width;
    final direction = liked ? 1.0 : -1.0;
    final begin = from ?? _dragOffset;
    final end = Offset(direction * width * 1.45, begin.dy + 72);

    _pendingLiked = liked;
    _isAnimating = true;
    _revealController.stop();
    _snapController.stop();
    _flyAnimation = Tween<Offset>(begin: begin, end: end).animate(
      CurvedAnimation(parent: _flyController, curve: Curves.easeInCubic),
    );
    _flyController.forward(from: 0);
  }

  void _snapBack() {
    if (_isAnimating || _isTrainingCompleted) return;
    _isAnimating = true;
    _flyController.stop();
    _snapAnimation = Tween<Offset>(begin: _dragOffset, end: Offset.zero)
        .animate(
          CurvedAnimation(parent: _snapController, curve: Curves.elasticOut),
        );
    _snapController.forward(from: 0);
  }

  void _onPanStart(DragStartDetails _) {
    if (_isAnimating || _isTrainingCompleted) return;
    _flyController.stop();
    _snapController.stop();
  }

  void _onPanUpdate(DragUpdateDetails details) {
    if (_isAnimating || _isTrainingCompleted) return;
    setState(() => _dragOffset += details.delta);
  }

  void _onPanEnd(DragEndDetails details) {
    if (_isAnimating || _isTrainingCompleted) return;
    final width = MediaQuery.of(context).size.width;
    final threshold = width * 0.20;
    final velocity = details.velocity.pixelsPerSecond.dx;

    if (_dragOffset.dx.abs() > threshold || velocity.abs() > 760) {
      final liked = velocity.abs() > 760 ? velocity > 0 : _dragOffset.dx > 0;
      HapticFeedback.mediumImpact();
      _flyOff(liked);
    } else {
      _snapBack();
    }
  }

  @override
  Widget build(BuildContext context) {
    final resumeError = _resumeError;
    if (_isResumeLoading || resumeError != null) {
      return AppScaffold(
        title: 'AI 취향 학습',
        child: Stack(
          children: [
            if (resumeError != null)
              Positioned(
                top: 10,
                right: 18,
                child: SessionKillButton(
                  isLoading: _isKillingSession,
                  onPressed: _killSession,
                ),
              ),
            Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: SoftCard(
                  padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
                  child: resumeError == null
                      ? const VerificationStatusContent(
                          completed: false,
                          title: '취향 기록 확인 중...',
                          subtitle: '이전에 넘긴 카드가 있는지 확인하고 있어요.',
                        )
                      : Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              CupertinoIcons.exclamationmark_triangle,
                              color: Color(0xFFDC2626),
                              size: 34,
                            ),
                            const SizedBox(height: 14),
                            const Text(
                              '이어가기 실패',
                              style: TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                            const SizedBox(height: 10),
                            Text(
                              resumeError,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontSize: 14,
                                height: 1.55,
                                fontWeight: FontWeight.w600,
                                color: AppColors.textSub,
                              ),
                            ),
                            const SizedBox(height: 18),
                            PrimaryButton(
                              text: '다시 확인하기',
                              onPressed: _retryLoadSavedTasteProgress,
                            ),
                          ],
                        ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    final progress = (_index + 1) / _cards.length;
    final nextCard = _index + 1 < _cards.length ? _cards[_index + 1] : null;
    final dragProgress = (_dragOffset.dx.abs() / 150).clamp(0.0, 1.0);

    return AppScaffold(
      title: 'AI 취향 학습',
      child: Stack(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                StepHeader(
                  current: 2,
                  total: 2,
                  title: '끌리는 분위기를 골라주세요',
                  subtitle: '오른쪽으로 스와이프해 좋아요, 왼쪽으로 스와이프해 별로에요!',
                ),
                const SizedBox(height: 18),
                ClipRRect(
                  borderRadius: BorderRadius.circular(99),
                  child: LinearProgressIndicator(
                    value: progress,
                    minHeight: 9,
                    color: AppColors.primary,
                    backgroundColor: AppColors.border,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  '${_index + 1} / ${_cards.length}',
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: AppColors.primary,
                  ),
                ),
                const SizedBox(height: 18),
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, constraints) {
                      final cardHeight = math.min(520.0, constraints.maxHeight);
                      final nextScale = 0.94 + (0.04 * dragProgress);
                      final nextYOffset = 18 - (12 * dragProgress);
                      final rotation = (_dragOffset.dx / 340).clamp(
                        -0.22,
                        0.22,
                      );
                      final topScale = 0.98 + (0.02 * _revealProgress);
                      final topYOffset = 6 * (1 - _revealProgress);

                      return Center(
                        child: SizedBox(
                          height: cardHeight,
                          width: double.infinity,
                          child: Stack(
                            clipBehavior: Clip.none,
                            alignment: Alignment.center,
                            children: [
                              if (nextCard != null)
                                Positioned.fill(
                                  child: Transform.translate(
                                    offset: Offset(0, nextYOffset),
                                    child: Transform.scale(
                                      scale: nextScale,
                                      child: Opacity(
                                        opacity: 0.82 + (0.18 * dragProgress),
                                        child: TasteProfileCard(
                                          key: ValueKey('next-${nextCard.id}'),
                                          data: nextCard,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              Positioned.fill(
                                child: GestureDetector(
                                  onPanStart: _onPanStart,
                                  onPanUpdate: _onPanUpdate,
                                  onPanEnd: _onPanEnd,
                                  child: Transform.translate(
                                    offset: _dragOffset + Offset(0, topYOffset),
                                    child: Transform.scale(
                                      scale: topScale,
                                      child: Transform.rotate(
                                        angle: rotation.toDouble(),
                                        child: Stack(
                                          fit: StackFit.expand,
                                          children: [
                                            TasteProfileCard(
                                              key: ValueKey(
                                                'active-${_cards[_index].id}',
                                              ),
                                              data: _cards[_index],
                                            ),
                                            if (dragProgress > 0)
                                              SwipeDecisionBadge(
                                                liked: _dragOffset.dx > 0,
                                                opacity: dragProgress,
                                              ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 18),
                Row(
                  children: [
                    Expanded(
                      child: SecondaryButton(
                        text: '별로에요',
                        icon: CupertinoIcons.xmark,
                        onPressed: () => _programmaticSwipe(false),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: PrimaryButton(
                        text: '좋아요',
                        icon: CupertinoIcons.heart_fill,
                        onPressed: () => _programmaticSwipe(true),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          TasteCompletionOverlay(visible: _isTrainingCompleted),
        ],
      ),
    );
  }
}

class TasteCompletionOverlay extends StatelessWidget {
  final bool visible;

  const TasteCompletionOverlay({super.key, required this.visible});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      ignoring: !visible,
      child: AnimatedOpacity(
        opacity: visible ? 1 : 0,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        child: Container(
          width: double.infinity,
          height: double.infinity,
          color: visible ? AppColors.background : Colors.transparent,
          alignment: Alignment.center,
          padding: const EdgeInsets.all(26),
          child: AnimatedScale(
            scale: visible ? 1 : 0.96,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            child: const SoftCard(
              padding: EdgeInsets.fromLTRB(22, 24, 22, 22),
              child: VerificationStatusContent(
                completed: true,
                title: '취향 분석이 완료되었어요!',
                subtitle: 'AI가 오늘의 인연을 준비하는 화면으로 이동할게요.',
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class TasteCardData {
  final String id;
  final String gender;
  final int number;
  final String code;
  final String imagePath;
  final String imageUrl;
  final List<Color> colors;

  const TasteCardData({
    required this.id,
    required this.gender,
    required this.number,
    required this.code,
    required this.imagePath,
    required this.imageUrl,
    required this.colors,
  });
}

class _TastePhotoError extends StatelessWidget {
  const _TastePhotoError();

  @override
  Widget build(BuildContext context) {
    return const ColoredBox(
      color: AppColors.background,
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(22),
          child: Text(
            'AI 프로필 사진을 불러오지 못했어요.',
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 15,
              height: 1.45,
              fontWeight: FontWeight.w800,
              color: AppColors.textSub,
            ),
          ),
        ),
      ),
    );
  }
}

class TasteNetworkPhoto extends StatelessWidget {
  final TasteCardData data;

  const TasteNetworkPhoto({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return Image.network(
      data.imageUrl,
      fit: BoxFit.cover,
      filterQuality: FilterQuality.medium,
      gaplessPlayback: false,
      webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
      errorBuilder: (context, error, stackTrace) {
        return const _TastePhotoError();
      },
      loadingBuilder: (context, child, loadingProgress) {
        if (loadingProgress == null) return child;
        return ColoredBox(
          color: AppColors.background,
          child: const Center(
            child: CircularProgressIndicator(color: AppColors.primary),
          ),
        );
      },
    );
  }
}

class TasteProfileCard extends StatelessWidget {
  final TasteCardData data;

  const TasteProfileCard({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(maxHeight: 520),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(34),
        boxShadow: [
          BoxShadow(
            color: data.colors.first.withValues(alpha: 0.24),
            blurRadius: 34,
            offset: const Offset(0, 14),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        fit: StackFit.expand,
        children: [TasteNetworkPhoto(data: data)],
      ),
    );
  }
}

class SwipeDecisionBadge extends StatelessWidget {
  final bool liked;
  final double opacity;

  const SwipeDecisionBadge({
    super.key,
    required this.liked,
    required this.opacity,
  });

  @override
  Widget build(BuildContext context) {
    final color = liked ? AppColors.mint : const Color(0xFFEF4444);
    final text = liked ? '좋아요' : '별로에요';
    final alignment = liked ? Alignment.topLeft : Alignment.topRight;

    return Positioned.fill(
      child: Align(
        alignment: alignment,
        child: Padding(
          padding: const EdgeInsets.all(22),
          child: Opacity(
            opacity: opacity.clamp(0.0, 1.0),
            child: Transform.rotate(
              angle: liked ? -0.16 : 0.16,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 18,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.92),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(color: color, width: 2),
                  boxShadow: [
                    BoxShadow(
                      color: color.withValues(alpha: 0.18),
                      blurRadius: 18,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Text(
                  text,
                  style: TextStyle(
                    color: color,
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class WaitingScreen extends StatefulWidget {
  const WaitingScreen({super.key});

  @override
  State<WaitingScreen> createState() => _WaitingScreenState();
}

class _WaitingScreenState extends State<WaitingScreen> {
  bool _notificationReady = false;
  bool _isLoggingOut = false;
  FestivalEventSchedule? _eventSchedule;
  StreamSubscription<FestivalEventSchedule?>? _scheduleSubscription;
  Timer? _revealTimer;
  Timer? _countdownTicker;

  @override
  void initState() {
    super.initState();
    _scheduleSubscription = FestivalBackend.instance
        .watchEventSchedule()
        .listen(_handleScheduleUpdate);
    unawaited(
      FestivalBackend.instance.loadEventSchedule().then((schedule) {
        if (!mounted) return;
        _handleScheduleUpdate(schedule);
      }),
    );
    unawaited(_loadNotificationState());
  }

  void _handleScheduleUpdate(FestivalEventSchedule? schedule) {
    if (!mounted) return;
    setState(() => _eventSchedule = schedule);
    _revealTimer?.cancel();
    _countdownTicker?.cancel();

    if (schedule == null || !schedule.enabled) return;

    if (schedule.areRecommendationsRevealed()) {
      _goToMatches();
      return;
    }

    _countdownTicker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      if (_eventSchedule?.areRecommendationsRevealed() == true) {
        _goToMatches();
        return;
      }
      setState(() {});
    });

    final wait = schedule.timeUntilReveal();
    if (wait > Duration.zero) {
      _revealTimer = Timer(
        wait + const Duration(milliseconds: 500),
        _goToMatches,
      );
    }
  }

  void _goToMatches() {
    if (!mounted || _isLoggingOut) return;
    Navigator.of(context).pushReplacementNamed(AppRoutes.matches);
  }

  Future<void> _confirmLogout() async {
    if (_isLoggingOut) return;
    HapticFeedback.selectionClick();
    final shouldLogout = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          title: const Text(
            '로그아웃할까요?',
            style: TextStyle(fontWeight: FontWeight.w900),
          ),
          content: const Text(
            '현재 기기에서 입장 코드 세션이 사라지고, 다시 이용하려면 코드를 다시 입력해야 해요.',
            style: TextStyle(
              height: 1.45,
              color: AppColors.textSub,
              fontWeight: FontWeight.w600,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('취소'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('로그아웃'),
            ),
          ],
        );
      },
    );
    if (shouldLogout != true) return;

    _revealTimer?.cancel();
    _countdownTicker?.cancel();
    setState(() => _isLoggingOut = true);
    try {
      await FestivalBackend.instance.logout();
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(AppRoutes.access, (route) => false);
    } catch (_) {
      if (!mounted) return;
      showAppSnack(context, '로그아웃에 실패했어요. 잠시 후 다시 시도해주세요.');
      setState(() => _isLoggingOut = false);
    }
  }

  @override
  void dispose() {
    _revealTimer?.cancel();
    _countdownTicker?.cancel();
    _scheduleSubscription?.cancel();
    super.dispose();
  }

  Future<void> _loadNotificationState() async {
    final status = await FestivalPushService.instance
        .currentAuthorizationStatus();
    if (!mounted) return;
    setState(() {
      _notificationReady =
          status == AuthorizationStatus.authorized ||
          status == AuthorizationStatus.provisional;
    });
  }

  void _showNotificationSheet() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(22, 8, 22, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '알림 준비',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900),
                ),
                const SizedBox(height: 10),
                const Text(
                  '홈 화면에 추가된 웹앱에서 알림 권한을 허용하면 결과 공개와 새 채팅을 알려드릴게요.',
                  style: TextStyle(
                    height: 1.55,
                    fontSize: 15,
                    color: AppColors.textSub,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 18),
                PrimaryButton(
                  text: '알림 켜기',
                  onPressed: () async {
                    final hint = FestivalPushService.instance.iosHomeScreenHint;
                    if (hint != null) {
                      Navigator.of(context).pop();
                      if (!context.mounted) return;
                      showAppSnack(context, hint);
                      return;
                    }

                    final result = await FestivalPushService.instance
                        .requestPermissionAndSyncDetailed();
                    if (!context.mounted) return;
                    Navigator.of(context).pop();
                    setState(() => _notificationReady = result.success);
                    showAppSnack(context, result.debugMessage);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final schedule = _eventSchedule;
    final lockClock = schedule != null
        ? schedule.formatClockKst(schedule.profileTasteLockAt)
        : '19:30';
    final batchClock = schedule != null
        ? schedule.formatClockKst(schedule.batchRecommendationsAt)
        : '19:31';
    final revealClock = schedule != null
        ? schedule.formatClockKst(schedule.recommendationsRevealAt)
        : '20:00';
    final revealHeadline = '$revealClock에 추천 프로필이 공개돼요';
    final canOpenMatches =
        schedule == null ||
        !schedule.enabled ||
        schedule.areRecommendationsRevealed();
    final wait = schedule?.timeUntilReveal() ?? Duration.zero;
    final countdown = wait == Duration.zero
        ? null
        : (wait.inHours > 0
              ? '${wait.inHours}시간 ${wait.inMinutes.remainder(60)}분'
              : wait.inMinutes > 0
              ? '${wait.inMinutes.remainder(60)}분 ${wait.inSeconds.remainder(60)}초'
              : '${wait.inSeconds.remainder(60)}초');

    return AppScaffold(
      title: '오늘의 인연',
      showBack: false,
      trailing: TextButton(
        onPressed: _isLoggingOut ? null : _confirmLogout,
        style: TextButton.styleFrom(
          foregroundColor: AppColors.textSub,
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        child: Text(
          _isLoggingOut ? '로그아웃 중…' : '로그아웃',
          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800),
        ),
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(20, 10, 20, 28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SoftCard(
              padding: const EdgeInsets.all(22),
              color: AppColors.blush,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const StatusPill(
                    text: '1차 매칭 준비 중',
                    color: AppColors.primary,
                  ),
                  const SizedBox(height: 18),
                  Text(
                    revealHeadline,
                    style: const TextStyle(
                      fontSize: 28,
                      height: 1.2,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    schedule?.isInBatchWindow() == true
                        ? '지금 CLIP으로 프로필·취향이 완료된 참가자들의 추천을 계산하고 있어요. $revealClock에 카드가 열려요.'
                        : '프로필·AI 취향 입력이 $lockClock에 마감되고, $batchClock부터 CLIP 매칭이 시작돼요. $revealClock에 추천 카드가 공개됩니다.',
                    style: const TextStyle(
                      fontSize: 15,
                      height: 1.55,
                      color: AppColors.textSub,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Expanded(
                        child: TimeBox(label: '마감', value: lockClock),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TimeBox(label: '계산', value: batchClock),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TimeBox(label: '공개', value: revealClock),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            SoftCard(
              padding: const EdgeInsets.all(18),
              child: Column(
                children: [
                  RoundStepRow(
                    icon: CupertinoIcons.check_mark_circled_solid,
                    title: '프로필 등록 완료',
                    subtitle: '닉네임, 성별, 학과, 나이, MBTI 저장됨',
                    active: true,
                  ),
                  const Divider(height: 24, color: AppColors.border),
                  RoundStepRow(
                    icon: CupertinoIcons.sparkles,
                    title: 'AI 취향 학습 완료',
                    subtitle: '20장 스와이프 응답 반영 대기',
                    active: true,
                  ),
                  const Divider(height: 24, color: AppColors.border),
                  RoundStepRow(
                    icon: CupertinoIcons.person_2_fill,
                    title: '추천 결과 공개 예정',
                    subtitle: '결과는 공개 후에도 사라지지 않아요',
                    active: false,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 18),
            InfoBanner(
              icon: _notificationReady
                  ? CupertinoIcons.bell_fill
                  : CupertinoIcons.bell,
              text: _notificationReady
                  ? '알림 받을 준비가 되었어요.'
                  : '결과 공개와 새 채팅 알림을 놓치지 않게 준비해둘 수 있어요.',
              color: _notificationReady ? AppColors.mint : AppColors.primary,
              actionText: _notificationReady ? null : '알림 켜기',
              onAction: _showNotificationSheet,
            ),
            const SizedBox(height: 14),
            SecondaryButton(
              text: '친구에게 공유하기',
              icon: CupertinoIcons.square_arrow_up,
              onPressed: () => showAppSnack(context, '공유 링크가 준비되는 위치예요.'),
            ),
            const SizedBox(height: 10),
            SecondaryButton(
              text: _isLoggingOut ? '로그아웃 중…' : '로그아웃',
              icon: CupertinoIcons.square_arrow_right,
              onPressed: _isLoggingOut ? null : _confirmLogout,
            ),
          ],
        ),
      ),
      bottomBar: PrimaryButton(
        text: canOpenMatches
            ? '추천 결과 보기'
            : countdown != null
            ? '$revealClock 공개 · $countdown 남음'
            : '$revealClock에 공개됩니다',
        onPressed: canOpenMatches && !_isLoggingOut ? _goToMatches : null,
      ),
    );
  }
}

class TodayMatchScreen extends StatefulWidget {
  const TodayMatchScreen({super.key});

  @override
  State<TodayMatchScreen> createState() => _TodayMatchScreenState();
}

enum HomeTab { recommendation, chats }

class _TodayMatchScreenState extends State<TodayMatchScreen> {
  int _currentIndex = 0;
  HomeTab _activeTab = HomeTab.recommendation;
  final Set<int> _revealedCards = <int>{};
  late final PageController _pageController;
  Future<void>? _matchImagePrecache;
  List<FestivalProfile?> _recommendationSlots = List<FestivalProfile?>.filled(
    3,
    null,
  );
  bool _isLoadingRecommendations = true;
  bool _isSyncingPush = false;
  bool _notificationReady = false;
  bool _recommendationsFrozen = false;
  String? _recommendationError;
  String? _targetGender;
  int _availableCandidateCount = 0;
  FestivalEventSchedule? _eventSchedule;
  StreamSubscription<FestivalEventSchedule?>? _scheduleSubscription;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(viewportFraction: 0.82);
    _scheduleSubscription = FestivalBackend.instance
        .watchEventSchedule()
        .listen(_handleEventSchedule);
    unawaited(_redirectIfWaitingForReveal());
    unawaited(_loadNotificationState());
  }

  Future<void> _redirectIfWaitingForReveal() async {
    if (!await FestivalBackend.instance.isWaitingForRecommendationReveal()) {
      return;
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacementNamed(AppRoutes.waiting);
  }

  void _handleEventSchedule(FestivalEventSchedule? schedule) {
    if (!mounted) return;
    setState(() => _eventSchedule = schedule);

    if (schedule != null &&
        schedule.enabled &&
        !schedule.areRecommendationsRevealed()) {
      Navigator.of(context).pushReplacementNamed(AppRoutes.waiting);
      return;
    }

    if (schedule == null || schedule.areRecommendationsRevealed()) {
      if (_recommendationsFrozen) return;
      unawaited(_refreshRecommendations(freezeAfterLoad: schedule != null));
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _matchImagePrecache ??= precacheImage(
      const AssetImage(_profileCardImageAsset),
      context,
    );
  }

  @override
  void dispose() {
    _scheduleSubscription?.cancel();
    _pageController.dispose();
    super.dispose();
  }

  void _revealCard(int index) {
    HapticFeedback.mediumImpact();
    final profile = _recommendationSlots[index];
    if (profile == null) {
      setState(() => _revealedCards.add(index));
      return;
    }
    final imageReady =
        _matchImagePrecache ??
        precacheImage(const AssetImage(_profileCardImageAsset), context);
    imageReady.whenComplete(() {
      if (!mounted) return;
      setState(() => _revealedCards.add(index));
    });
  }

  void _openProfile(FestivalProfile profile) {
    Navigator.of(context).pushNamed(AppRoutes.profile, arguments: profile);
  }

  void _selectHomeTab(HomeTab tab) {
    if (_activeTab == tab) return;
    HapticFeedback.selectionClick();
    setState(() => _activeTab = tab);
  }

  void _openChat(FestivalProfile profile) {
    Navigator.of(context).pushNamed(AppRoutes.chat, arguments: profile);
  }

  Future<void> _loadNotificationState() async {
    final status = await FestivalPushService.instance
        .currentAuthorizationStatus();
    if (!mounted) return;
    setState(() {
      _notificationReady =
          status == AuthorizationStatus.authorized ||
          status == AuthorizationStatus.provisional;
    });
    if (_notificationReady) {
      final result = await FestivalPushService.instance
          .syncTokenSafelyDetailed();
      if (mounted && !result.success) {
        debugPrint('[FESTIVAL_PUSH] auto sync failed: ${result.debugMessage}');
        setState(() => _notificationReady = false);
      }
    }
  }

  Future<void> _enableNotifications() async {
    if (_isSyncingPush) return;
    HapticFeedback.selectionClick();

    final hint = FestivalPushService.instance.iosHomeScreenHint;
    if (hint != null) {
      showAppSnack(context, hint);
      return;
    }

    setState(() => _isSyncingPush = true);
    final result = await FestivalPushService.instance
        .requestPermissionAndSyncDetailed();
    if (!mounted) return;
    setState(() {
      _isSyncingPush = false;
      _notificationReady = result.success;
    });
    showAppSnack(context, result.debugMessage);
  }

  Future<void> _confirmLogout() async {
    HapticFeedback.selectionClick();
    final shouldLogout = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          title: const Text(
            '로그아웃할까요?',
            style: TextStyle(fontWeight: FontWeight.w900),
          ),
          content: const Text(
            '현재 기기에서 입장 코드 세션이 사라지고, 다시 이용하려면 코드를 다시 입력해야 해요.',
            style: TextStyle(
              height: 1.45,
              color: AppColors.textSub,
              fontWeight: FontWeight.w600,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('취소'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('로그아웃'),
            ),
          ],
        );
      },
    );
    if (shouldLogout != true) return;

    await FestivalBackend.instance.logout();
    if (!mounted) return;
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(AppRoutes.access, (route) => false);
  }

  Future<void> _refreshRecommendations({
    bool refreshOnServer = false,
    bool freezeAfterLoad = false,
  }) async {
    if (_recommendationsFrozen) return;
    HapticFeedback.selectionClick();
    setState(() {
      _isLoadingRecommendations = true;
      _recommendationError = null;
      _currentIndex = 0;
      _revealedCards.clear();
    });
    if (_pageController.hasClients) {
      _pageController.jumpToPage(0);
    }

    try {
      final bundle = await FestivalBackend.instance
          .loadPersonalizedRecommendations(refreshOnServer: refreshOnServer);
      if (!mounted) return;
      setState(() {
        _recommendationSlots = bundle.slots;
        _targetGender = bundle.targetGender;
        _availableCandidateCount = bundle.availableCount;
        _isLoadingRecommendations = false;
        if (freezeAfterLoad) _recommendationsFrozen = true;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _recommendationError = error is FestivalBackendException
            ? error.message
            : '추천 프로필을 불러오지 못했어요.';
        _recommendationSlots = List<FestivalProfile?>.filled(3, null);
        _availableCandidateCount = 0;
        _isLoadingRecommendations = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      showBack: false,
      backgroundColor: Colors.white,
      bottomBar: HomeBottomTabs(
        selected: _activeTab,
        onSelected: _selectHomeTab,
      ),
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 180),
        switchInCurve: Curves.easeOutCubic,
        switchOutCurve: Curves.easeInCubic,
        child: _activeTab == HomeTab.recommendation
            ? _buildRecommendationTab()
            : _buildChatsTab(),
      ),
    );
  }

  Widget _buildRecommendationTab() {
    return Padding(
      key: const ValueKey('recommendation-tab'),
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(99),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.sparkles,
                      size: 14,
                      color: AppColors.primary,
                    ),
                    SizedBox(width: 5),
                    Text(
                      'AI CURATED',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w900,
                        color: AppColors.primary,
                      ),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              IconButton(
                tooltip: '로그아웃',
                onPressed: _confirmLogout,
                icon: const Icon(CupertinoIcons.square_arrow_right, size: 18),
                color: AppColors.textSub,
                padding: const EdgeInsets.all(6),
                constraints: const BoxConstraints(minWidth: 34, minHeight: 34),
                visualDensity: VisualDensity.compact,
              ),
              if (_eventSchedule == null || !_eventSchedule!.enabled)
                TextButton.icon(
                  onPressed: _isLoadingRecommendations
                      ? null
                      : () => _refreshRecommendations(refreshOnServer: true),
                  icon: const Icon(CupertinoIcons.arrow_clockwise, size: 15),
                  label: const Text('추천 새로고침'),
                  style: TextButton.styleFrom(
                    foregroundColor: AppColors.textSub,
                    textStyle: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w900,
                    ),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 9,
                      vertical: 6,
                    ),
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          const Text(
            '오늘의 인연',
            style: TextStyle(
              fontSize: 34,
              height: 1.05,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '카드를 넘겨보고 마음에 드는 인연을 열어보세요.',
            style: TextStyle(
              fontSize: 15,
              height: 1.45,
              color: AppColors.textSub,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (_targetGender != null) ...[
            const SizedBox(height: 12),
            Text(
              '현재 등록된 $_targetGender 프로필 $_availableCandidateCount명 중 취향 기반으로 계산한 디버깅 화면이에요.',
              style: const TextStyle(
                fontSize: 12,
                height: 1.35,
                color: AppColors.textHint,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
          const SizedBox(height: 18),
          Expanded(
            child: _isLoadingRecommendations
                ? const Center(child: CircularProgressIndicator())
                : _recommendationError != null
                ? RecommendationErrorState(
                    message: _recommendationError!,
                    onRetry: () => _refreshRecommendations(),
                  )
                : Column(
                    children: [
                      Expanded(
                        child: PageView.builder(
                          controller: _pageController,
                          physics: const PageScrollPhysics(),
                          itemCount: _recommendationSlots.length,
                          onPageChanged: (index) {
                            HapticFeedback.selectionClick();
                            setState(() => _currentIndex = index);
                          },
                          itemBuilder: (context, index) {
                            final profile = _recommendationSlots[index];
                            final isActive = index == _currentIndex;
                            return AnimatedScale(
                              scale: isActive ? 1.0 : 0.94,
                              duration: const Duration(milliseconds: 260),
                              curve: Curves.easeOutCubic,
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 7,
                                  vertical: 8,
                                ),
                                child: MysteryMatchCard(
                                  profile: profile,
                                  index: index,
                                  isActive: isActive,
                                  isRevealed: _revealedCards.contains(index),
                                  onReveal: () => _revealCard(index),
                                  onOpen: profile == null
                                      ? null
                                      : () => _openProfile(profile),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 14),
                      MatchPageDots(
                        count: _recommendationSlots.length,
                        currentIndex: _currentIndex,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        _revealedCards.contains(_currentIndex)
                            ? (_recommendationSlots[_currentIndex] == null
                                  ? '현재 조건에 맞는 추천 인원이 부족해요.'
                                  : '카드를 한 번 더 누르면 상세 프로필로 이동해요.')
                            : '앞면이 궁금한 카드를 탭해서 공개해보세요.',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 13,
                          height: 1.35,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textSub,
                        ),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildChatsTab() {
    return Padding(
      key: const ValueKey('chats-tab'),
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '채팅',
            style: TextStyle(
              fontSize: 34,
              height: 1.05,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '오늘의 인연과 이어진 대화를 확인해요.',
            style: TextStyle(
              fontSize: 15,
              height: 1.45,
              color: AppColors.textSub,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 18),
          Expanded(
            child: StreamBuilder<List<ChatPreview>>(
              stream: FestivalBackend.instance.watchChatPreviews(),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                final chats = snapshot.data ?? const <ChatPreview>[];
                if (chats.isEmpty) {
                  return const Center(
                    child: SoftCard(
                      padding: EdgeInsets.fromLTRB(22, 24, 22, 22),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(
                            CupertinoIcons.chat_bubble_2,
                            color: AppColors.primary,
                            size: 34,
                          ),
                          SizedBox(height: 12),
                          Text(
                            '아직 대화가 없어요',
                            style: TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            '추천 프로필에서 첫 채팅을 보내면 이곳에 대화가 쌓여요.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 14,
                              height: 1.45,
                              color: AppColors.textSub,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }

                return ListView.separated(
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.only(bottom: 18),
                  itemBuilder: (context, index) {
                    final preview = chats[index];
                    return ChatPreviewTile(
                      preview: preview,
                      onTap: () => _openChat(preview.profile),
                    );
                  },
                  separatorBuilder: (context, index) =>
                      const SizedBox(height: 10),
                  itemCount: chats.length,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class RecommendationErrorState extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const RecommendationErrorState({
    super.key,
    required this.message,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SoftCard(
        padding: const EdgeInsets.all(22),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              CupertinoIcons.exclamationmark_triangle,
              color: AppColors.primary,
              size: 34,
            ),
            const SizedBox(height: 12),
            const Text(
              '추천을 불러오지 못했어요',
              style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 8),
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 14,
                height: 1.45,
                color: AppColors.textSub,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 16),
            SecondaryButton(
              text: '다시 불러오기',
              icon: CupertinoIcons.arrow_clockwise,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}

class ChatPreview {
  final String roomId;
  final FestivalProfile profile;
  final String latestMessage;
  final String time;
  final int unreadCount;
  final DateTime lastMessageAt;

  const ChatPreview({
    required this.roomId,
    required this.profile,
    required this.latestMessage,
    required this.time,
    required this.unreadCount,
    required this.lastMessageAt,
  });

  factory ChatPreview.fromRoomDoc(
    QueryDocumentSnapshot<Map<String, dynamic>> doc,
    FestivalSession session,
  ) {
    final data = doc.data();
    final ticketIds =
        (data['participantTicketIds'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    final counterpartTicketId = ticketIds.firstWhere(
      (ticketId) => ticketId != session.ticketId,
      orElse: () => '',
    );
    if (counterpartTicketId.isEmpty) {
      throw const FormatException('Missing counterpart ticket');
    }

    final profiles = data['participantProfiles'];
    final profileData = profiles is Map
        ? Map<String, dynamic>.from(profiles[counterpartTicketId] as Map? ?? {})
        : <String, dynamic>{};
    final lastMessageAt =
        _readDate(data['latestMessageAt']) ??
        DateTime.fromMillisecondsSinceEpoch(0);
    final unreadFor = data['unreadFor'];
    final hasUnread = unreadFor is Map && unreadFor[session.uid] == true;

    return ChatPreview(
      roomId: doc.id,
      profile: _festivalProfileFromChatSnapshot(
        counterpartTicketId,
        profileData,
      ),
      latestMessage: data['latestMessage'] as String? ?? '아직 메시지가 없어요.',
      time: _formatChatTime(lastMessageAt),
      unreadCount: hasUnread ? 1 : 0,
      lastMessageAt: lastMessageAt,
    );
  }

  factory ChatPreview.fromMembershipDoc(
    QueryDocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data();
    final counterpartTicketId = data['counterpartTicketId'] as String? ?? '';
    if (counterpartTicketId.isEmpty) {
      throw const FormatException('Missing counterpart ticket');
    }

    final profile = data['counterpartProfile'];
    final profileData = profile is Map
        ? Map<String, dynamic>.from(profile)
        : <String, dynamic>{};
    final lastMessageAt =
        _readDate(data['latestMessageAt']) ??
        DateTime.fromMillisecondsSinceEpoch(0);

    return ChatPreview(
      roomId: data['roomId'] as String? ?? doc.id,
      profile: _festivalProfileFromChatSnapshot(
        counterpartTicketId,
        profileData,
      ),
      latestMessage: data['latestMessage'] as String? ?? '아직 메시지가 없어요.',
      time: _formatChatTime(lastMessageAt),
      unreadCount: data['unread'] == true ? 1 : 0,
      lastMessageAt: lastMessageAt,
    );
  }
}

FestivalProfile _festivalProfileFromChatSnapshot(
  String ticketId,
  Map<String, dynamic> data,
) {
  final photoUrl = FestivalAvatarDisplayResolver.resolve(data);
  return FestivalProfile(
    id: ticketId,
    name: data['name'] as String? ?? '익명',
    age: data['age'] is int ? data['age'] as int : 20,
    gender: data['gender'] as String? ?? '',
    department: data['department'] as String? ?? '',
    studentAffiliationLabel:
        data['studentAffiliationLabel'] as String? ??
        _studentAffiliationText(data['studentAffiliation'] as String?),
    mbti: data['mbti'] as String? ?? '',
    intro: (data['intro'] as String?)?.trim().isNotEmpty == true
        ? data['intro'] as String
        : '아직 자기소개를 적지 않았어요.',
    matchPercent: 86,
    tags: const [],
    colors: const [AppColors.primary, AppColors.blush],
    photoUrl: photoUrl.isEmpty ? null : photoUrl,
  );
}

class HomeBottomTabs extends StatelessWidget {
  final HomeTab selected;
  final ValueChanged<HomeTab> onSelected;

  const HomeBottomTabs({
    super.key,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 58,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.input,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: _HomeBottomTabButton(
              label: '추천',
              icon: CupertinoIcons.sparkles,
              selected: selected == HomeTab.recommendation,
              onTap: () => onSelected(HomeTab.recommendation),
            ),
          ),
          const SizedBox(width: 4),
          Expanded(
            child: _HomeBottomTabButton(
              label: '채팅',
              icon: CupertinoIcons.chat_bubble_2_fill,
              selected: selected == HomeTab.chats,
              onTap: () => onSelected(HomeTab.chats),
            ),
          ),
        ],
      ),
    );
  }
}

class _HomeBottomTabButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  const _HomeBottomTabButton({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: double.infinity,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? AppColors.surface : Colors.transparent,
          borderRadius: BorderRadius.circular(16),
          boxShadow: selected
              ? [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.08),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              size: 19,
              color: selected ? AppColors.primary : AppColors.textSub,
            ),
            const SizedBox(width: 7),
            Text(
              label,
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w900,
                color: selected ? AppColors.primary : AppColors.textSub,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ChatPreviewTile extends StatelessWidget {
  final ChatPreview preview;
  final VoidCallback onTap;

  const ChatPreviewTile({
    super.key,
    required this.preview,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        HapticFeedback.selectionClick();
        onTap();
      },
      child: Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppColors.border.withValues(alpha: 0.78)),
        ),
        child: Row(
          children: [
            ProfileAvatar(profile: preview.profile, size: 52),
            const SizedBox(width: 13),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          preview.profile.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                            color: AppColors.textMain,
                          ),
                        ),
                      ),
                      Text(
                        preview.time,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textHint,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${preview.profile.department} • ${preview.profile.mbti}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w800,
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(height: 5),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          preview.latestMessage,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: AppColors.textSub,
                          ),
                        ),
                      ),
                      if (preview.unreadCount > 0) ...[
                        const SizedBox(width: 8),
                        Container(
                          height: 22,
                          constraints: const BoxConstraints(minWidth: 22),
                          alignment: Alignment.center,
                          padding: const EdgeInsets.symmetric(horizontal: 7),
                          decoration: BoxDecoration(
                            color: AppColors.primary,
                            borderRadius: BorderRadius.circular(99),
                          ),
                          child: Text(
                            '${preview.unreadCount}',
                            style: const TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w900,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MysteryMatchCard extends StatefulWidget {
  final FestivalProfile? profile;
  final int index;
  final bool isActive;
  final bool isRevealed;
  final VoidCallback onReveal;
  final VoidCallback? onOpen;

  const MysteryMatchCard({
    super.key,
    required this.profile,
    required this.index,
    required this.isActive,
    required this.isRevealed,
    required this.onReveal,
    required this.onOpen,
  });

  @override
  State<MysteryMatchCard> createState() => _MysteryMatchCardState();
}

class _MysteryMatchCardState extends State<MysteryMatchCard>
    with SingleTickerProviderStateMixin, AutomaticKeepAliveClientMixin {
  late final AnimationController _controller;
  late final Animation<double> _flipAnimation;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 700),
      vsync: this,
      value: widget.isRevealed ? 1 : 0,
    );
    _flipAnimation = CurvedAnimation(
      parent: _controller,
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  void didUpdateWidget(covariant MysteryMatchCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isRevealed != oldWidget.isRevealed) {
      if (widget.isRevealed) {
        _controller.forward();
      } else {
        _controller.reverse();
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _handleTap() {
    if (!widget.isActive || _controller.isAnimating) return;
    if (widget.isRevealed) {
      if (widget.profile == null || widget.onOpen == null) return;
      HapticFeedback.lightImpact();
      widget.onOpen!();
    } else {
      widget.onReveal();
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: _handleTap,
      child: AnimatedBuilder(
        animation: _flipAnimation,
        builder: (context, child) {
          final angle = _flipAnimation.value * math.pi;
          final showProfileFace = _flipAnimation.value >= 0.5;
          final profile = widget.profile;
          final face = RepaintBoundary(
            child: showProfileFace
                ? Transform(
                    alignment: Alignment.center,
                    transform: Matrix4.identity()..rotateY(math.pi),
                    child: profile == null
                        ? ShortageMatchFace(isActive: widget.isActive)
                        : MatchProfileFace(
                            profile: profile,
                            isActive: widget.isActive,
                            onOpen: widget.onOpen!,
                          ),
                  )
                : MysteryCardFace(
                    index: widget.index,
                    isActive: widget.isActive,
                  ),
          );

          return Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.001)
              ..rotateY(angle),
            child: face,
          );
        },
      ),
    );
  }
}

class MysteryCardFace extends StatelessWidget {
  final int index;
  final bool isActive;

  const MysteryCardFace({
    super.key,
    required this.index,
    required this.isActive,
  });

  @override
  Widget build(BuildContext context) {
    final cardNumber = (index + 1).toString().padLeft(2, '0');

    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.78)),
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: AppColors.primary.withValues(alpha: 0.18),
                  blurRadius: 48,
                  offset: const Offset(0, 18),
                ),
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.06),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ]
            : null,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Stack(
          fit: StackFit.expand,
          alignment: Alignment.center,
          children: [
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      AppColors.blush,
                      Colors.white,
                      AppColors.primary.withValues(alpha: 0.10),
                    ],
                    stops: const [0.0, 0.48, 1.0],
                  ),
                ),
              ),
            ),
            Positioned.fill(
              child: CustomPaint(painter: _MysteryPatternPainter()),
            ),
            Positioned(
              top: 24,
              left: 24,
              right: 24,
              child: Align(
                alignment: Alignment.centerRight,
                child: Text(
                  cardNumber,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w900,
                    color: AppColors.primary.withValues(alpha: 0.58),
                  ),
                ),
              ),
            ),
            Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 136,
                    height: 136,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.primary.withValues(alpha: 0.09),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.primary.withValues(
                            alpha: isActive ? 0.22 : 0.12,
                          ),
                          blurRadius: isActive ? 36 : 22,
                          spreadRadius: isActive ? 3 : 0,
                        ),
                      ],
                    ),
                    child: const Text(
                      '?',
                      style: TextStyle(
                        fontSize: 104,
                        height: 1,
                        fontWeight: FontWeight.w900,
                        color: AppColors.primary,
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    '오늘의 인연 카드',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 24,
                      height: 1.15,
                      fontWeight: FontWeight.w900,
                      color: AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    isActive ? '탭하여 프로필 공개하기' : '옆 카드도 확인해보세요',
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textSub,
                    ),
                  ),
                ],
              ),
            ),
            Positioned(
              left: 24,
              right: 24,
              bottom: 24,
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.78),
                  borderRadius: BorderRadius.circular(18),
                  border: Border.all(
                    color: AppColors.primary.withValues(alpha: 0.10),
                  ),
                ),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      CupertinoIcons.hand_draw,
                      size: 18,
                      color: AppColors.primary,
                    ),
                    SizedBox(width: 8),
                    Flexible(
                      child: Text(
                        '첫 공개 후에도 결과는 사라지지 않아요',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                          color: AppColors.primary,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ShortageMatchFace extends StatelessWidget {
  final bool isActive;

  const ShortageMatchFace({super.key, required this.isActive});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.78)),
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: AppColors.primary.withValues(alpha: 0.16),
                  blurRadius: 42,
                  offset: const Offset(0, 18),
                ),
              ]
            : null,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Stack(
          fit: StackFit.expand,
          children: [
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [AppColors.input, Colors.white, AppColors.blush],
                ),
              ),
            ),
            Positioned.fill(
              child: CustomPaint(painter: _MysteryPatternPainter()),
            ),
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.10),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(
                        Icons.group_off,
                        color: AppColors.primary,
                        size: 34,
                      ),
                    ),
                    const SizedBox(height: 20),
                    const Text(
                      '인원이 부족합니다!',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 26,
                        height: 1.12,
                        fontWeight: FontWeight.w900,
                        color: AppColors.textMain,
                      ),
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      '조건에 맞는 등록자가 아직 3명 미만이라 이 카드는 비어 있어요.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.45,
                        fontWeight: FontWeight.w700,
                        color: AppColors.textSub,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MatchProfileFace extends StatelessWidget {
  final FestivalProfile profile;
  final bool isActive;
  final VoidCallback onOpen;

  const MatchProfileFace({
    super.key,
    required this.profile,
    required this.isActive,
    required this.onOpen,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        boxShadow: isActive
            ? [
                BoxShadow(
                  color: AppColors.primary.withValues(alpha: 0.25),
                  blurRadius: 42,
                  offset: const Offset(0, 18),
                ),
              ]
            : null,
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Stack(
          fit: StackFit.expand,
          children: [
            ProfilePhotoImage(
              profile: profile,
              fallbackAsset: _profileCardImageAsset,
              fit: BoxFit.cover,
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    profile.colors.first.withValues(alpha: 0.12),
                    Colors.black.withValues(alpha: 0.12),
                    Colors.black.withValues(alpha: 0.78),
                  ],
                  stops: const [0.0, 0.48, 1.0],
                ),
              ),
            ),
            Positioned(
              top: 22,
              left: 22,
              right: 22,
              child: Row(
                children: [
                  _GlassPill(text: '${profile.matchPercent}% Match'),
                  const Spacer(),
                  _GlassIconButton(
                    tooltip: '상세 보기',
                    icon: CupertinoIcons.chevron_forward,
                    onPressed: onOpen,
                  ),
                ],
              ),
            ),
            Positioned(
              left: 22,
              right: 22,
              bottom: 22,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Expanded(
                        child: Text(
                          profile.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 32,
                            height: 1.05,
                            fontWeight: FontWeight.w900,
                            color: Colors.white,
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        '${profile.age}',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                          color: Colors.white.withValues(alpha: 0.88),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '${profile.department} • ${profile.mbti}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: Colors.white.withValues(alpha: 0.82),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: profile.tags.take(3).map((tag) {
                      return _GlassPill(text: tag, compact: true);
                    }).toList(),
                  ),
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: onOpen,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.textMain,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                      ),
                    ),
                    child: const Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '프로필 자세히 보기',
                          style: TextStyle(
                            fontSize: 15,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        SizedBox(width: 8),
                        Icon(CupertinoIcons.chevron_forward, size: 18),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class MatchPageDots extends StatelessWidget {
  final int count;
  final int currentIndex;

  const MatchPageDots({
    super.key,
    required this.count,
    required this.currentIndex,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: List.generate(count, (index) {
        final selected = index == currentIndex;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          width: selected ? 18 : 7,
          height: 7,
          decoration: BoxDecoration(
            color: selected
                ? AppColors.primary
                : AppColors.primary.withValues(alpha: 0.20),
            borderRadius: BorderRadius.circular(99),
          ),
        );
      }),
    );
  }
}

class SecondRoundEmptyCard extends StatelessWidget {
  final VoidCallback onRegister;

  const SecondRoundEmptyCard({super.key, required this.onRegister});

  @override
  Widget build(BuildContext context) {
    return SoftCard(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const StatusPill(text: '2차 준비 중', color: AppColors.amber),
          const SizedBox(height: 16),
          const Text(
            '2차 매칭권을 사용하면 새로운 카드가 이곳에 쌓여요.',
            style: TextStyle(
              fontSize: 20,
              height: 1.38,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 10),
          const Text(
            '1차 결과는 그대로 보관되고, 라운드별 추천을 따로 확인할 수 있어요.',
            style: TextStyle(
              fontSize: 14,
              height: 1.45,
              fontWeight: FontWeight.w600,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: 18),
          PrimaryButton(text: '2차 매칭권 등록', onPressed: onRegister),
        ],
      ),
    );
  }
}

class _GlassPill extends StatelessWidget {
  final String text;
  final bool compact;

  const _GlassPill({required this.text, this.compact = false});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 10 : 12,
        vertical: compact ? 6 : 8,
      ),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.28),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: compact ? 12 : 13,
          fontWeight: FontWeight.w800,
          color: Colors.white,
        ),
      ),
    );
  }
}

class _GlassIconButton extends StatelessWidget {
  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  const _GlassIconButton({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: GestureDetector(
        onTap: onPressed,
        child: Container(
          width: 40,
          height: 40,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.28),
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white.withValues(alpha: 0.16)),
          ),
          child: Icon(icon, color: Colors.white, size: 19),
        ),
      ),
    );
  }
}

class _MysteryPatternPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.primary.withValues(alpha: 0.055)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    const spacing = 34.0;

    for (double x = -size.height; x < size.width; x += spacing) {
      canvas.drawLine(
        Offset(x, 0),
        Offset(x + size.height, size.height),
        paint,
      );
    }
    for (double x = 0; x < size.width + size.height; x += spacing) {
      canvas.drawLine(
        Offset(x, 0),
        Offset(x - size.height, size.height),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class ProfileDetailScreen extends StatelessWidget {
  final FestivalProfile profile;

  const ProfileDetailScreen({super.key, required this.profile});

  void _showMore(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 6, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SheetAction(
                  icon: CupertinoIcons.exclamationmark_bubble,
                  title: '신고하기',
                  subtitle: '운영자가 확인할 신고 사유를 남겨요.',
                  destructive: true,
                  onTap: () {
                    Navigator.of(context).pop();
                    showFestivalReportSheet(
                      context,
                      profile: profile,
                      source: 'profile_detail',
                    );
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _showFirstChatNotice(BuildContext context) async {
    HapticFeedback.selectionClick();
    final confirmed = await showGeneralDialog<bool>(
      context: context,
      barrierDismissible: true,
      barrierLabel: '닫기',
      barrierColor: Colors.black.withValues(alpha: 0.72),
      transitionDuration: const Duration(milliseconds: 220),
      pageBuilder: (context, animation, secondaryAnimation) {
        return FirstChatNoticeDialog(profile: profile);
      },
      transitionBuilder: (context, animation, secondaryAnimation, child) {
        final curved = CurvedAnimation(
          parent: animation,
          curve: Curves.easeOutCubic,
          reverseCurve: Curves.easeInCubic,
        );
        return FadeTransition(
          opacity: curved,
          child: ScaleTransition(
            scale: Tween<double>(begin: 0.96, end: 1).animate(curved),
            child: child,
          ),
        );
      },
    );

    if (confirmed == true && context.mounted) {
      Navigator.of(context).pushNamed(AppRoutes.chat, arguments: profile);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: '프로필 상세',
      backgroundColor: AppColors.blush,
      trailing: IconButton(
        tooltip: '더보기',
        onPressed: () => _showMore(context),
        icon: const Icon(CupertinoIcons.ellipsis),
        color: AppColors.textMain,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(18, 8, 18, 32),
        child: SoftCard(
          padding: EdgeInsets.zero,
          radius: 32,
          clip: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                height: 440,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    ProfilePhotoImage(
                      profile: profile,
                      fallbackAsset: 'assets/images/aiprofile.png',
                      fit: BoxFit.cover,
                    ),
                    DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Colors.transparent,
                            Colors.black.withValues(alpha: 0.70),
                          ],
                        ),
                      ),
                    ),
                    Positioned(
                      top: 18,
                      left: 18,
                      child: StatusPill(
                        text: '${profile.matchPercent}% 잘 맞음',
                        color: AppColors.primary,
                      ),
                    ),
                    Positioned(
                      left: 22,
                      right: 22,
                      bottom: 24,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            profile.name,
                            style: const TextStyle(
                              fontSize: 36,
                              fontWeight: FontWeight.w900,
                              color: Colors.white,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 7,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(99),
                              border: Border.all(
                                color: Colors.white.withValues(alpha: 0.24),
                              ),
                            ),
                            child: Text(
                              profile.studentAffiliationLabel,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 13,
                                fontWeight: FontWeight.w900,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(22, 20, 22, 28),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionTitle('기본 정보'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        InfoChip(label: '나이', value: '${profile.age}세'),
                        InfoChip(label: '학과', value: profile.department),
                        InfoChip(
                          label: '소속',
                          value: profile.studentAffiliationLabel,
                        ),
                        InfoChip(label: 'MBTI', value: profile.mbti),
                      ],
                    ),
                    const SizedBox(height: 22),
                    const SectionTitle('저는 이런 사람이에요'),
                    const SizedBox(height: 10),
                    Text(
                      profile.intro,
                      style: const TextStyle(
                        fontSize: 16,
                        height: 1.65,
                        fontWeight: FontWeight.w600,
                        color: AppColors.textSub,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      bottomBar: PrimaryButton(
        text: '채팅 보내기',
        icon: CupertinoIcons.chat_bubble_text_fill,
        onPressed: () => _showFirstChatNotice(context),
      ),
    );
  }
}

class FirstChatNoticeDialog extends StatelessWidget {
  final FestivalProfile profile;

  const FirstChatNoticeDialog({super.key, required this.profile});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Material(
            color: Colors.transparent,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.fromLTRB(22, 22, 22, 20),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(28),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.22),
                    blurRadius: 36,
                    offset: const Offset(0, 18),
                  ),
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        child: const Icon(
                          CupertinoIcons.chat_bubble_2_fill,
                          color: AppColors.primary,
                          size: 24,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          '${profile.name}님에게\n첫 채팅을 보내기 전에',
                          style: const TextStyle(
                            fontSize: 23,
                            height: 1.25,
                            fontWeight: FontWeight.w900,
                            color: AppColors.textMain,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    '첫 메시지를 보내면 내 프로필과 사진도 상대에게 공개돼요.',
                    style: TextStyle(
                      fontSize: 19,
                      height: 1.45,
                      fontWeight: FontWeight.w900,
                      color: AppColors.textMain,
                    ),
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    '단순히 얼굴만 확인하려고 채팅을 보내는 건 상대에게 부담이 될 수 있어요. 정말 대화를 시작해보고 싶은 상대에게만 신중하게 보내주세요.',
                    style: TextStyle(
                      fontSize: 16,
                      height: 1.55,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textSub,
                    ),
                  ),
                  const SizedBox(height: 18),
                  const _NoticePoint(
                    icon: CupertinoIcons.person_crop_circle_badge_checkmark,
                    text: '내 프로필과 사진이 상대에게 함께 공개돼요',
                  ),
                  const SizedBox(height: 10),
                  const _NoticePoint(
                    icon: CupertinoIcons.bell_fill,
                    text: '상대에게 새 채팅 알림이 전달될 수 있어요',
                  ),
                  const SizedBox(height: 20),
                  PrimaryButton(
                    text: '이해했어요, 채팅 시작',
                    icon: CupertinoIcons.chat_bubble_text_fill,
                    textFontSize: 18,
                    onPressed: () => Navigator.of(context).pop(true),
                  ),
                  const SizedBox(height: 10),
                  SecondaryButton(
                    text: '조금 더 볼게요',
                    textFontSize: 17,
                    onPressed: () => Navigator.of(context).pop(false),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NoticePoint extends StatelessWidget {
  final IconData icon;
  final String text;

  const _NoticePoint({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 28,
          height: 28,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: AppColors.blush,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, size: 16, color: AppColors.primary),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 15,
                height: 1.35,
                fontWeight: FontWeight.w800,
                color: AppColors.textMain,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class ChatScreen extends StatefulWidget {
  final FestivalProfile profile;

  const ChatScreen({super.key, required this.profile});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  late final Stream<List<ChatMessage>> _messagesStream;
  bool _isSending = false;

  @override
  void initState() {
    super.initState();
    final roomId = FestivalBackend.instance.chatRoomIdFor(widget.profile);
    FestivalPushService.instance.setOpenedChatRoom(roomId);
    _messagesStream = FestivalBackend.instance.watchChatMessages(
      widget.profile,
    );
    _runSilently(FestivalBackend.instance.markChatRead(widget.profile));
  }

  @override
  void dispose() {
    FestivalPushService.instance.setOpenedChatRoom(null);
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _isSending) return;
    _controller.clear();
    setState(() => _isSending = true);
    try {
      await FestivalBackend.instance.saveChatMessage(widget.profile, text);
    } catch (error) {
      if (!mounted) return;
      _controller.text = text;
      _controller.selection = TextSelection.collapsed(offset: text.length);
      final message = error is FestivalBackendException
          ? error.message
          : '메시지 전송에 실패했어요. 잠시 후 다시 시도해주세요.';
      showAppSnack(context, message);
    } finally {
      if (mounted) setState(() => _isSending = false);
    }
  }

  void _showChatMenu() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 6, 20, 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                SheetAction(
                  icon: CupertinoIcons.exclamationmark_bubble,
                  title: '대화 신고하기',
                  subtitle: '신고된 대화만 운영자가 확인해요.',
                  destructive: true,
                  onTap: () {
                    Navigator.of(context).pop();
                    showFestivalReportSheet(
                      context,
                      profile: widget.profile,
                      source: 'chat_screen',
                      roomId: FestivalBackend.instance.chatRoomIdFor(
                        widget.profile,
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return AppScaffold(
      title: widget.profile.name,
      resizeToAvoidBottomInset: false,
      keyboardResizeFactor: 1,
      onTitleTap: () {
        HapticFeedback.selectionClick();
        Navigator.of(
          context,
        ).pushNamed(AppRoutes.profile, arguments: widget.profile);
      },
      trailing: IconButton(
        tooltip: '채팅 메뉴',
        onPressed: _showChatMenu,
        icon: const Icon(CupertinoIcons.ellipsis),
        color: AppColors.textMain,
      ),
      child: Column(
        children: [
          Container(
            margin: const EdgeInsets.fromLTRB(20, 4, 20, 10),
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.blush,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              children: [
                ProfileAvatar(profile: widget.profile, size: 48),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${widget.profile.department} • ${widget.profile.mbti}',
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                          color: AppColors.primary,
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        '1차 오늘의 인연에서 연결됨',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: AppColors.textSub,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: StreamBuilder<List<ChatMessage>>(
              stream: _messagesStream,
              builder: (context, snapshot) {
                final messages = snapshot.data ?? const <ChatMessage>[];
                if (snapshot.hasError) {
                  return const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        '채팅을 불러오지 못했어요. 입장 코드 세션을 다시 확인해주세요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 15,
                          height: 1.45,
                          color: AppColors.textSub,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  );
                }
                if (messages.any((message) => !message.mine)) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    _runSilently(
                      FestivalBackend.instance.markChatRead(widget.profile),
                    );
                  });
                }
                if (snapshot.connectionState == ConnectionState.waiting) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (messages.isEmpty) {
                  return const Center(
                    child: Padding(
                      padding: EdgeInsets.all(24),
                      child: Text(
                        '첫 메시지를 보내면 대화가 시작돼요.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 15,
                          height: 1.45,
                          color: AppColors.textSub,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  );
                }

                return ListView.builder(
                  reverse: true,
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
                  itemCount: messages.length,
                  itemBuilder: (context, index) {
                    return ChatBubble(message: messages[index]);
                  },
                );
              },
            ),
          ),
          _ChatComposerBar(
            controller: _controller,
            isSending: _isSending,
            onSend: _send,
          ),
        ],
      ),
    );
  }
}

class _ChatComposerBar extends StatelessWidget {
  final TextEditingController controller;
  final bool isSending;
  final VoidCallback onSend;

  const _ChatComposerBar({
    required this.controller,
    required this.isSending,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.background,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 18,
            offset: const Offset(0, -8),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => onSend(),
                  enabled: !isSending,
                  scrollPadding: const EdgeInsets.only(bottom: 120),
                  decoration: InputDecoration(
                    hintText: '메시지 보내기',
                    hintStyle: const TextStyle(
                      color: AppColors.textHint,
                      fontWeight: FontWeight.w600,
                    ),
                    filled: true,
                    fillColor: AppColors.input,
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(18),
                      borderSide: const BorderSide(color: AppColors.border),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(18),
                      borderSide: const BorderSide(color: AppColors.border),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(18),
                      borderSide: const BorderSide(color: AppColors.primary),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              SizedBox(
                width: 48,
                height: 48,
                child: FilledButton(
                  onPressed: isSending ? null : onSend,
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                    padding: EdgeInsets.zero,
                  ),
                  child: isSending
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(CupertinoIcons.arrow_up, size: 22),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ChatMessage {
  final String text;
  final String time;
  final bool mine;

  const ChatMessage({
    required this.text,
    required this.time,
    required this.mine,
  });

  factory ChatMessage.fromMessageDoc(
    QueryDocumentSnapshot<Map<String, dynamic>> doc, {
    required String currentTicketId,
    required String currentUid,
  }) {
    final data = doc.data();
    final senderTicketId = data['senderTicketId'] as String?;
    return ChatMessage(
      text: data['text'] as String? ?? '',
      time: _formatChatTime(data['createdAt']),
      mine: senderTicketId?.isNotEmpty == true
          ? senderTicketId == currentTicketId
          : data['senderUid'] == currentUid,
    );
  }
}

class ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const ChatBubble({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final bubbleColor = message.mine ? AppColors.primary : AppColors.surface;
    final textColor = message.mine ? Colors.white : AppColors.textMain;

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: message.mine
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (message.mine)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: Text(
                message.time,
                style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.textHint,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          Flexible(
            child: Container(
              constraints: const BoxConstraints(maxWidth: 310),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
              decoration: BoxDecoration(
                color: bubbleColor,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(18),
                  topRight: const Radius.circular(18),
                  bottomLeft: Radius.circular(message.mine ? 18 : 5),
                  bottomRight: Radius.circular(message.mine ? 5 : 18),
                ),
                border: message.mine
                    ? null
                    : Border.all(color: AppColors.border),
              ),
              child: Text(
                message.text,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.45,
                  color: textColor,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
          if (!message.mine)
            Padding(
              padding: const EdgeInsets.only(left: 6),
              child: Text(
                message.time,
                style: const TextStyle(
                  fontSize: 11,
                  color: AppColors.textHint,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class PrimaryButton extends StatelessWidget {
  final String text;
  final VoidCallback? onPressed;
  final IconData? icon;
  final double textFontSize;

  const PrimaryButton({
    super.key,
    required this.text,
    this.onPressed,
    this.icon,
    this.textFontSize = 16,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      width: double.infinity,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primaryDeep,
          foregroundColor: Colors.white,
          disabledBackgroundColor: AppColors.primary.withValues(alpha: 0.36),
          disabledForegroundColor: Colors.white.withValues(alpha: 0.78),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 20),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: textFontSize,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SecondaryButton extends StatelessWidget {
  final String text;
  final VoidCallback? onPressed;
  final IconData? icon;
  final double textFontSize;

  const SecondaryButton({
    super.key,
    required this.text,
    this.onPressed,
    this.icon,
    this.textFontSize = 15,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 56,
      width: double.infinity,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textMain,
          side: const BorderSide(color: AppColors.border),
          backgroundColor: AppColors.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 19),
              const SizedBox(width: 8),
            ],
            Flexible(
              child: Text(
                text,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: textFontSize,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class SoftCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  final double radius;
  final bool clip;

  const SoftCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.color = AppColors.surface,
    this.radius = 24,
    this.clip = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding,
      clipBehavior: clip ? Clip.antiAlias : Clip.none,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: AppColors.border.withValues(alpha: 0.78)),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.06),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: child,
    );
  }
}

class SessionKillButton extends StatelessWidget {
  final bool isLoading;
  final VoidCallback onPressed;

  const SessionKillButton({
    super.key,
    required this.isLoading,
    required this.onPressed,
  });

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: TextButton.icon(
        onPressed: isLoading ? null : onPressed,
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primaryDeep,
          disabledForegroundColor: AppColors.textHint,
          padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          minimumSize: Size.zero,
        ),
        icon: isLoading
            ? const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(CupertinoIcons.trash, size: 15),
        label: Text(
          isLoading ? '초기화 중' : '세션 kill',
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w900),
        ),
      ),
    );
  }
}

class OnboardingRedirectScreen extends StatefulWidget {
  const OnboardingRedirectScreen({super.key});

  @override
  State<OnboardingRedirectScreen> createState() =>
      _OnboardingRedirectScreenState();
}

class _OnboardingRedirectScreenState extends State<OnboardingRedirectScreen> {
  String? _errorText;
  bool _isKillingSession = false;

  @override
  void initState() {
    super.initState();
    unawaited(_routeToSavedStep());
  }

  Future<void> _routeToSavedStep() async {
    setState(() => _errorText = null);

    try {
      final progress = await FestivalBackend.instance.loadOnboardingProgress();
      await Future<void>.delayed(const Duration(milliseconds: 280));
      if (!mounted) return;

      switch (progress.nextStep) {
        case FestivalNextStep.profile:
          Navigator.of(context).pushReplacementNamed(AppRoutes.signup);
        case FestivalNextStep.taste:
          Navigator.of(context).pushReplacementNamed(
            AppRoutes.taste,
            arguments: progress.tasteResume,
          );
        case FestivalNextStep.waiting:
          final route = await FestivalBackend.instance.matchesOrWaitingRoute();
          if (!mounted) return;
          Navigator.of(context).pushReplacementNamed(route);
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _errorText = error is FestivalBackendException
            ? error.message
            : '진행 상태를 확인하지 못했어요.';
      });
    }
  }

  Future<void> _killSession() async {
    if (_isKillingSession) return;
    setState(() => _isKillingSession = true);
    try {
      await FestivalBackend.instance.logout();
      if (!mounted) return;
      Navigator.of(
        context,
      ).pushNamedAndRemoveUntil(AppRoutes.access, (route) => false);
    } catch (_) {
      if (!mounted) return;
      showAppSnack(context, '세션 초기화에 실패했어요. 잠시 후 다시 시도해주세요.');
      setState(() => _isKillingSession = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final errorText = _errorText;
    return AppScaffold(
      showBack: false,
      backgroundColor: AppColors.desktopBackground,
      child: Stack(
        children: [
          if (errorText != null)
            Positioned(
              top: 14,
              right: 18,
              child: SessionKillButton(
                isLoading: _isKillingSession,
                onPressed: _killSession,
              ),
            ),
          Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: SoftCard(
                padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
                child: errorText == null
                    ? const VerificationStatusContent(
                        completed: false,
                        title: '진행 상태 확인 중...',
                        subtitle: '저장된 매칭권을 확인하고 이어갈 화면을 찾고 있어요.',
                      )
                    : Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(
                            CupertinoIcons.exclamationmark_triangle,
                            color: Color(0xFFDC2626),
                            size: 34,
                          ),
                          const SizedBox(height: 14),
                          const Text(
                            '이어가기 실패',
                            style: TextStyle(
                              fontSize: 24,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            errorText,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontSize: 14,
                              height: 1.55,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textSub,
                            ),
                          ),
                          const SizedBox(height: 18),
                          PrimaryButton(
                            text: '다시 확인하기',
                            onPressed: _routeToSavedStep,
                          ),
                        ],
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class AppTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hintText;
  final int minLines;
  final int maxLines;
  final TextCapitalization textCapitalization;
  final bool useMeongiFont;
  final FocusNode? focusNode;
  final EdgeInsets scrollPadding;

  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hintText,
    this.minLines = 1,
    this.maxLines = 1,
    this.textCapitalization = TextCapitalization.none,
    this.useMeongiFont = false,
    this.focusNode,
    this.scrollPadding = const EdgeInsets.all(20),
  });

  @override
  Widget build(BuildContext context) {
    final inputFormatters = useMeongiFont
        ? <TextInputFormatter>[
            TextInputFormatter.withFunction((oldValue, newValue) {
              final filtered = newValue.text.toUpperCase().replaceAll(
                RegExp('[^A-Z0-9]'),
                '',
              );
              final limited = filtered.length > 6
                  ? filtered.substring(0, 6)
                  : filtered;
              return TextEditingValue(
                text: limited,
                selection: TextSelection.collapsed(offset: limited.length),
                composing: TextRange.empty,
              );
            }),
          ]
        : null;

    final textField = TextField(
      controller: controller,
      focusNode: focusNode,
      minLines: minLines,
      maxLines: maxLines,
      keyboardType: useMeongiFont
          ? TextInputType.emailAddress
          : TextInputType.text,
      textInputAction: TextInputAction.done,
      textCapitalization: textCapitalization,
      autocorrect: !useMeongiFont,
      enableSuggestions: !useMeongiFont,
      enableIMEPersonalizedLearning: !useMeongiFont,
      smartDashesType: useMeongiFont
          ? SmartDashesType.disabled
          : SmartDashesType.enabled,
      smartQuotesType: useMeongiFont
          ? SmartQuotesType.disabled
          : SmartQuotesType.enabled,
      inputFormatters: inputFormatters,
      scrollPadding: scrollPadding,
      textAlign: useMeongiFont ? TextAlign.center : TextAlign.start,
      cursorColor: useMeongiFont ? Colors.transparent : AppColors.primary,
      style: TextStyle(
        fontFamily: useMeongiFont ? AppFonts.meongi : null,
        fontSize: useMeongiFont ? 60 : 16,
        height: useMeongiFont ? 1.0 : null,
        fontWeight: useMeongiFont ? FontWeight.w600 : FontWeight.w700,
        color: useMeongiFont ? Colors.transparent : AppColors.textMain,
        decoration: TextDecoration.none,
      ),
      decoration: InputDecoration(
        hintText: useMeongiFont ? '' : hintText,
        hintStyle: TextStyle(
          fontFamily: useMeongiFont ? AppFonts.meongi : null,
          fontSize: useMeongiFont ? 60 : null,
          height: useMeongiFont ? 1.0 : null,
          color: useMeongiFont
              ? AppColors.textSub.withValues(alpha: 0.48)
              : AppColors.textHint,
          fontWeight: useMeongiFont ? FontWeight.w600 : FontWeight.w600,
        ),
        filled: true,
        fillColor: useMeongiFont ? Colors.white : AppColors.input,
        contentPadding: EdgeInsets.symmetric(
          horizontal: 16,
          vertical: useMeongiFont ? 13 : 15,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
      ),
    );

    return FieldLabel(
      text: label,
      child: useMeongiFont
          ? Stack(
              alignment: Alignment.center,
              children: [
                textField,
                Positioned.fill(
                  child: IgnorePointer(
                    child: Center(
                      child: ValueListenableBuilder<TextEditingValue>(
                        valueListenable: controller,
                        builder: (context, value, _) {
                          return Text(
                            value.text,
                            maxLines: 1,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontFamily: AppFonts.meongi,
                              fontSize: 60,
                              height: 1.0,
                              fontWeight: FontWeight.w600,
                              color: AppColors.textMain,
                              decoration: TextDecoration.none,
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                ),
              ],
            )
          : textField,
    );
  }
}

class FieldLabel extends StatelessWidget {
  final String text;
  final Widget child;

  const FieldLabel({super.key, required this.text, required this.child});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          text,
          style: const TextStyle(
            fontSize: 14,
            color: AppColors.textSub,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        child,
      ],
    );
  }
}

class SegmentedOptions extends StatelessWidget {
  final List<String> values;
  final String selected;
  final ValueChanged<String> onSelected;

  const SegmentedOptions({
    super.key,
    required this.values,
    required this.selected,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.input,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        children: values.map((value) {
          final isSelected = value == selected;
          return Expanded(
            child: GestureDetector(
              onTap: () {
                HapticFeedback.selectionClick();
                onSelected(value);
              },
              child: Container(
                height: 44,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: isSelected ? AppColors.surface : Colors.transparent,
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: AppColors.primary.withValues(alpha: 0.08),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ]
                      : null,
                ),
                child: Text(
                  value,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w900,
                    color: isSelected ? AppColors.primary : AppColors.textSub,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class MbtiAxisSelector extends StatelessWidget {
  final String top;
  final String bottom;
  final String selected;
  final ValueChanged<String> onChanged;

  const MbtiAxisSelector({
    super.key,
    required this.top,
    required this.bottom,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _MbtiLetterButton(
          text: top,
          isSelected: selected == top,
          onTap: () => onChanged(top),
        ),
        const SizedBox(height: 6),
        _MbtiLetterButton(
          text: bottom,
          isSelected: selected == bottom,
          onTap: () => onChanged(bottom),
        ),
      ],
    );
  }
}

class _MbtiLetterButton extends StatelessWidget {
  final String text;
  final bool isSelected;
  final VoidCallback onTap;

  const _MbtiLetterButton({
    required this.text,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () {
        HapticFeedback.selectionClick();
        onTap();
      },
      child: Container(
        height: 46,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isSelected ? AppColors.surface : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected
                ? AppColors.primary.withValues(alpha: 0.22)
                : Colors.transparent,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: AppColors.primary.withValues(alpha: 0.08),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Text(
          text,
          style: TextStyle(
            fontFamily: AppFonts.meongi,
            fontSize: 29,
            height: 1.0,
            fontWeight: FontWeight.w900,
            color: isSelected ? AppColors.primaryDeep : AppColors.textSub,
          ),
        ),
      ),
    );
  }
}

class StepHeader extends StatelessWidget {
  final int current;
  final int total;
  final String title;
  final String subtitle;

  const StepHeader({
    super.key,
    required this.current,
    required this.total,
    required this.title,
    required this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        StatusPill(text: '$current / $total', color: AppColors.primary),
        const SizedBox(height: 12),
        Text(
          title,
          style: const TextStyle(
            fontSize: 28,
            height: 1.18,
            fontWeight: FontWeight.w900,
          ),
        ),
        const SizedBox(height: 9),
        Text(
          subtitle,
          style: const TextStyle(
            fontSize: 15,
            height: 1.48,
            color: AppColors.textSub,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class StatusPill extends StatelessWidget {
  final String text;
  final Color color;

  const StatusPill({super.key, required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: color.withValues(alpha: 0.16)),
      ),
      child: Text(
        text,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w900,
          color: color,
        ),
      ),
    );
  }
}

class TagChip extends StatelessWidget {
  final String text;

  const TagChip({super.key, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.blush,
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.12)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w800,
          color: AppColors.primaryDeep,
        ),
      ),
    );
  }
}

class InfoChip extends StatelessWidget {
  final String label;
  final String value;

  const InfoChip({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.input,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.textSub,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            value,
            style: const TextStyle(
              fontSize: 13,
              color: AppColors.textMain,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class SectionTitle extends StatelessWidget {
  final String text;

  const SectionTitle(this.text, {super.key});

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        fontSize: 16,
        fontWeight: FontWeight.w900,
        color: AppColors.textMain,
      ),
    );
  }
}

class InfoBanner extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;
  final String? actionText;
  final VoidCallback? onAction;

  const InfoBanner({
    super.key,
    required this.icon,
    required this.text,
    required this.color,
    this.actionText,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return SoftCard(
      color: color.withValues(alpha: 0.08),
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(15),
            ),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 14,
                height: 1.45,
                fontWeight: FontWeight.w700,
                color: AppColors.textMain,
              ),
            ),
          ),
          if (actionText != null) ...[
            const SizedBox(width: 10),
            TextButton(
              onPressed: onAction,
              child: Text(
                actionText!,
                style: TextStyle(color: color, fontWeight: FontWeight.w900),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class TimeBox extends StatelessWidget {
  final String label;
  final String value;

  const TimeBox({super.key, required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        children: [
          Text(
            label,
            style: const TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: AppColors.textSub,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            value,
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w900,
              color: AppColors.textMain,
            ),
          ),
        ],
      ),
    );
  }
}

class RoundStepRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool active;

  const RoundStepRow({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.active,
  });

  @override
  Widget build(BuildContext context) {
    final color = active ? AppColors.primary : AppColors.textHint;
    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.10),
            borderRadius: BorderRadius.circular(16),
          ),
          child: Icon(icon, color: color),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w900,
                  color: AppColors.textMain,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                subtitle,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textSub,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class ProfilePhotoImage extends StatelessWidget {
  final FestivalProfile profile;
  final String fallbackAsset;
  final BoxFit fit;

  const ProfilePhotoImage({
    super.key,
    required this.profile,
    required this.fallbackAsset,
    required this.fit,
  });

  @override
  Widget build(BuildContext context) {
    final photoUrl = profile.photoUrl;
    if (photoUrl == null || photoUrl.isEmpty) {
      return Image.asset(fallbackAsset, fit: fit);
    }

    return Image.network(
      photoUrl,
      fit: fit,
      filterQuality: FilterQuality.medium,
      gaplessPlayback: true,
      webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
      errorBuilder: (context, error, stackTrace) {
        return Image.asset(fallbackAsset, fit: fit);
      },
      loadingBuilder: (context, child, loadingProgress) {
        if (loadingProgress == null) return child;
        return Stack(
          fit: StackFit.expand,
          children: [
            Image.asset(fallbackAsset, fit: fit),
            ColoredBox(
              color: Colors.black.withValues(alpha: 0.08),
              child: const Center(
                child: CircularProgressIndicator(color: Colors.white),
              ),
            ),
          ],
        );
      },
    );
  }
}

class ProfileAvatar extends StatelessWidget {
  final FestivalProfile profile;
  final double size;

  const ProfileAvatar({super.key, required this.profile, this.size = 44});

  @override
  Widget build(BuildContext context) {
    final photoUrl = profile.photoUrl;
    return Container(
      width: size,
      height: size,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: profile.colors),
        borderRadius: BorderRadius.circular(size * 0.35),
      ),
      child: photoUrl == null || photoUrl.isEmpty
          ? Center(
              child: Text(
                profile.name.characters.first,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: size * 0.42,
                  fontWeight: FontWeight.w900,
                ),
              ),
            )
          : Image.network(
              photoUrl,
              fit: BoxFit.cover,
              webHtmlElementStrategy: WebHtmlElementStrategy.fallback,
              errorBuilder: (context, error, stackTrace) {
                return Center(
                  child: Text(
                    profile.name.characters.first,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: size * 0.42,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                );
              },
            ),
    );
  }
}

const _festivalReportReasons = [
  '부적절한 사진',
  '부적절한 자기소개',
  '사칭 또는 허위 정보',
  '불쾌한 메시지',
  '기타',
];

Future<void> showReportSubmittedDialog(BuildContext context) {
  return showDialog<void>(
    context: context,
    barrierDismissible: true,
    builder: (dialogContext) {
      return Dialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 24, 22, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 52,
                height: 52,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  CupertinoIcons.check_mark,
                  color: AppColors.primary,
                  size: 26,
                ),
              ),
              const SizedBox(height: 16),
              const Text(
                '신고가 접수되었습니다',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 10),
              const Text(
                '운영팀이 내용을 확인한 뒤 필요한 조치를 진행할게요.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  height: 1.5,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textSub,
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.of(dialogContext).pop(),
                  style: FilledButton.styleFrom(
                    backgroundColor: AppColors.primaryDeep,
                    foregroundColor: Colors.white,
                    minimumSize: const Size.fromHeight(48),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(14),
                    ),
                  ),
                  child: const Text(
                    '확인',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}

Future<void> showFestivalReportSheet(
  BuildContext context, {
  required FestivalProfile profile,
  required String source,
  String? roomId,
}) {
  return showModalBottomSheet<void>(
    context: context,
    showDragHandle: true,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
    ),
    builder: (sheetContext) {
      return SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 22),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${profile.name}님 신고',
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                '운영자가 확인할 수 있도록 신고 내용이 저장돼요.',
                style: TextStyle(
                  fontSize: 14,
                  height: 1.45,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textSub,
                ),
              ),
              const SizedBox(height: 12),
              ..._festivalReportReasons.map(
                (reason) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    reason,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      color: AppColors.textMain,
                    ),
                  ),
                  trailing: const Icon(CupertinoIcons.chevron_forward),
                  onTap: () async {
                    Navigator.of(sheetContext).pop();
                    try {
                      await FestivalBackend.instance.submitUserReport(
                        reportedProfile: profile,
                        reason: reason,
                        source: source,
                        roomId: roomId,
                      );
                      if (!context.mounted) return;
                      await showReportSubmittedDialog(context);
                    } catch (error) {
                      if (!context.mounted) return;
                      showAppSnack(
                        context,
                        error is FestivalBackendException
                            ? error.message
                            : '신고 접수에 실패했어요.',
                      );
                    }
                  },
                ),
              ),
            ],
          ),
        ),
      );
    },
  );
}

class SheetAction extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool destructive;

  const SheetAction({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.destructive = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = destructive ? const Color(0xFFDC2626) : AppColors.textMain;
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
      leading: Container(
        width: 44,
        height: 44,
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.09),
          borderRadius: BorderRadius.circular(16),
        ),
        child: Icon(icon, color: color, size: 22),
      ),
      title: Text(
        title,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w900,
          color: color,
        ),
      ),
      subtitle: Text(
        subtitle,
        style: const TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: AppColors.textSub,
        ),
      ),
      onTap: onTap,
    );
  }
}

void showAppSnack(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(
      SnackBar(
        content: Text(
          message,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.textMain,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    );
}
