// =============================================================================
// 팀 구성(3명) 화면 — Firestore eventTeamSetups 실시간 동기화
// =============================================================================

import 'dart:async';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Colors, Icons;
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

import '../models/event_team_route_args.dart';
import '../../../router/route_names.dart';
import '../../../services/auth_service.dart';
import '../../../services/event_team_service.dart';
import '../../../services/team_meeting_request_service.dart';
import '../../../services/kakao_friend_invite_helper.dart';
import '../../../services/storage_service.dart';
import '../../../services/user_service.dart';

class _AppColors {
  static const Color primary = Color(0xFFF0426E);
  static const Color backgroundLight = Color(0xFFF8F6F6);
  static const Color surfaceLight = CupertinoColors.white;
  static const Color textMain = Color(0xFF181113);
  static const Color textSub = Color(0xFF9E9E9E);
  static const Color gray200 = Color(0xFFEEEEEE);
  static const Color gray400 = Color(0xFFBDBDBD);
  static const Color kakaoYellow = Color(0xFFFEE500);
  static const Color pendingSub = Color(0xFFABABAB);
}

class TeamSetupScreen extends StatefulWidget {
  const TeamSetupScreen({super.key});

  @override
  State<TeamSetupScreen> createState() => _TeamSetupScreenState();
}

class _TeamSetupScreenState extends State<TeamSetupScreen> {
  final StorageService _storage = StorageService();
  final AuthService _auth = AuthService();
  final UserService _userService = UserService();
  final EventTeamService _eventTeam = EventTeamService();

  String? _kakaoUserId;
  bool _sessionOk = false;
  String? _teamSetupId;
  bool _bootError = false;

  /// 첫 프레임에서 uid=null로 오인하지 않도록, 부트스트랩 완료 후에만 본문 분기
  bool _bootstrapComplete = false;

  /// Cloud Function 등에서 온 실제 사유 (Wi-Fi와 무관한 경우가 많음)
  String? _bootstrapErrorDetail;
  String _kakaoShareName = '친구';

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    final uid = await _storage.getKakaoUserId();
    if (!mounted) return;
    if (uid == null || uid.isEmpty) {
      setState(() {
        _kakaoUserId = uid;
        _bootError = false;
        _bootstrapComplete = true;
      });
      return;
    }
    // Firebase 커스텀 토큰 실패해도 ensureTeamSetup 내부에서 다시 시도하며,
    // 팀 문서 조회는 rules상 공개 read라 화면은 teamSetupId만 있으면 표시한다.
    final ok = await _auth.ensureFirebaseSessionForKakao(uid);
    if (!mounted) return;
    setState(() {
      _kakaoUserId = uid;
      _sessionOk = ok;
    });
    await _loadShareName(uid);
    try {
      final saved = await _storage.getEventTeamSetupDraftId(uid);
      final existingTeam = await _eventTeam.resolveCurrentTeamSetupForUser(
        uid,
        preferredTeamSetupId: saved,
      );
      if (existingTeam != null) {
        await _storage.saveEventTeamSetupDraftId(uid, existingTeam.teamSetupId);
        if (!mounted) return;
        setState(() {
          _teamSetupId = existingTeam.teamSetupId;
          _bootError = false;
          _bootstrapErrorDetail = null;
          _bootstrapComplete = true;
        });
        return;
      }
      if (saved != null && saved.isNotEmpty) {
        await _storage.clearEventTeamSetupDraftId(uid);
      }

      final id = await _eventTeam.ensureTeamSetup();
      await _storage.saveEventTeamSetupDraftId(uid, id);
      if (!mounted) return;
      setState(() {
        _teamSetupId = id;
        _bootError = false;
        _bootstrapErrorDetail = null;
        _bootstrapComplete = true;
      });
    } catch (e, st) {
      debugPrint('TeamSetup bootstrap: $e\n$st');
      final saved = await _storage.getEventTeamSetupDraftId(uid);
      final recovered = await _eventTeam.recoverTeamSetupIfLeader(
        kakaoUserId: uid,
        savedTeamSetupId: saved ?? '',
      );
      if (!mounted) return;
      if (recovered != null) {
        await _storage.saveEventTeamSetupDraftId(uid, recovered);
        setState(() {
          _teamSetupId = recovered;
          _bootError = false;
          _bootstrapErrorDetail = null;
          _bootstrapComplete = true;
        });
        return;
      }
      setState(() {
        _bootError = true;
        _bootstrapComplete = true;
        _bootstrapErrorDetail = _formatTeamBootstrapError(e);
      });
    }
  }

  String _formatTeamBootstrapError(Object e) {
    if (e is FirebaseFunctionsException) {
      final codeNorm = e.code.toLowerCase().replaceAll('_', '-');
      if (codeNorm == 'not-found') {
        return _firebaseFunctionsCodeHint('not-found');
      }
      final msg = e.message?.trim();
      if (msg != null && msg.isNotEmpty && msg.toUpperCase() != 'NOT_FOUND') {
        return msg;
      }
      return _firebaseFunctionsCodeHint(e.code);
    }
    if (e is StateError) return e.message;
    final s = e.toString();
    return s.replaceFirst('Exception: ', '').replaceFirst('StateError: ', '');
  }

  String _firebaseFunctionsCodeHint(String code) {
    switch (code.toLowerCase().replaceAll('_', '-')) {
      case 'not-found':
        return '팀용 서버 기능(ensureEventTeamSetup)을 찾을 수 없어요. '
            '프로젝트 `seolleyeon`에 Cloud Functions가 배포됐는지 확인하고, '
            '리전은 asia-northeast3이어야 해요. (`firebase deploy --only functions`)';
      case 'unauthenticated':
        return '서버에 로그인 정보가 전달되지 않았어요. 카카오 로그인 후 다시 시도해주세요.';
      case 'failed-precondition':
        return '연세 메일 인증·가입 정보를 서버에서 확인하지 못했어요. 학생 인증을 완료했는지 확인해주세요.';
      case 'permission-denied':
        return '이 팀 설정에 접근할 수 없어요.';
      case 'deadline-exceeded':
      case 'unavailable':
        return '서버 응답이 지연되고 있어요. 잠시 후 다시 시도해주세요.';
      default:
        return '팀을 불러오지 못했어요. ($code)';
    }
  }

  Future<void> _retryBootstrap() async {
    setState(() {
      _bootstrapComplete = false;
      _bootError = false;
      _bootstrapErrorDetail = null;
      _teamSetupId = null;
    });
    await _bootstrap();
  }

  Future<void> _loadShareName(String uid) async {
    final user = await _userService.getUserProfile(uid);
    if (!mounted || user == null) return;
    final raw = user['onboarding'];
    final ob = raw is Map
        ? Map<String, dynamic>.from(raw)
        : <String, dynamic>{};
    final n = ob['nickname']?.toString().trim().isNotEmpty == true
        ? ob['nickname'].toString()
        : (user['nickname']?.toString().trim().isNotEmpty == true
              ? user['nickname'].toString()
              : '친구');
    setState(() => _kakaoShareName = n);
  }

  Future<void> _openPicker() async {
    final uid = _kakaoUserId;
    if (uid == null || uid.isEmpty) return;
    if (!_sessionOk) {
      final ok = await _auth.ensureFirebaseSessionForVerifiedUser(uid);
      if (!mounted) return;
      setState(() => _sessionOk = ok);
      if (!ok) {
        _briefAlert('연결 상태를 확인한 뒤 다시 시도해주세요.');
        return;
      }
    }
    HapticFeedback.lightImpact();
    Navigator.of(context).pushNamed(RouteNames.eventAddFriend);
  }

  Future<void> _kakaoInvite() async {
    final uid = _kakaoUserId;
    if (uid == null || uid.isEmpty) {
      _briefAlert('로그인이 필요해요.');
      return;
    }
    if (!_sessionOk) {
      final ok = await _auth.ensureFirebaseSessionForKakao(uid);
      if (!mounted) return;
      setState(() => _sessionOk = ok);
      if (!ok) {
        _briefAlert('카카오·네트워크 연결을 확인한 뒤 다시 시도해주세요.');
        return;
      }
    }
    HapticFeedback.mediumImpact();
    try {
      await KakaoFriendInviteHelper.createAndShareKakaoInvite(
        inviterDisplayName: _kakaoShareName,
      );
    } catch (e) {
      if (mounted) {
        _briefAlert(e.toString().replaceFirst('Exception: ', ''));
      }
    }
  }

  void _briefAlert(String message) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(message),
        ),
        actions: [
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('확인'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final uid = _kakaoUserId;

    return CupertinoPageScaffold(
      backgroundColor: _AppColors.backgroundLight,
      child: Stack(
        children: [
          SafeArea(
            child: Column(
              children: [
                _Header(
                  onBack: () => Navigator.of(context).pop(),
                  teamSetupId: _teamSetupId,
                ),
                Expanded(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 24,
                      vertical: 16,
                    ),
                    child: Column(
                      children: [
                        const _HeadlineGroup(),
                        const SizedBox(height: 20),
                        if (_bootstrapComplete &&
                            _teamSetupId != null &&
                            uid != null &&
                            uid.isNotEmpty)
                          Align(
                            alignment: Alignment.centerRight,
                            child: CupertinoButton(
                              padding: EdgeInsets.zero,
                              minimumSize: const Size(40, 40),
                              onPressed: () {
                                HapticFeedback.selectionClick();
                                unawaited(_openPicker());
                              },
                              child: Container(
                                width: 40,
                                height: 40,
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.05),
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(
                                  CupertinoIcons.add_circled_solid,
                                  color: _AppColors.primary,
                                  size: 28,
                                ),
                              ),
                            ),
                          ),
                        const SizedBox(height: 8),
                        if (!_bootstrapComplete)
                          const Padding(
                            padding: EdgeInsets.all(48),
                            child: Center(child: CupertinoActivityIndicator()),
                          )
                        else if (uid == null || uid.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 48),
                            child: Text(
                              '팀을 구성하려면 로그인이 필요해요.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontFamily: 'Pretendard',
                                fontSize: 14,
                                height: 1.45,
                                color: _AppColors.textSub,
                              ),
                            ),
                          )
                        else if (_bootError || _teamSetupId == null)
                          Padding(
                            padding: const EdgeInsets.symmetric(
                              vertical: 32,
                              horizontal: 8,
                            ),
                            child: Column(
                              children: [
                                Text(
                                  _bootError
                                      ? (_bootstrapErrorDetail ??
                                            '팀 정보를 불러오지 못했어요.')
                                      : '팀을 준비하는 중이에요…',
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(
                                    fontFamily: 'Pretendard',
                                    fontSize: 14,
                                    height: 1.45,
                                    color: _AppColors.textSub,
                                  ),
                                ),
                                if (_bootError) ...[
                                  const SizedBox(height: 8),
                                  const Text(
                                    '와이파이가 아니라 로그인·연세 인증·서버 응답 문제일 수 있어요.',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontFamily: 'Pretendard',
                                      fontSize: 12,
                                      height: 1.4,
                                      color: _AppColors.textSub,
                                    ),
                                  ),
                                  const SizedBox(height: 16),
                                  CupertinoButton.filled(
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 24,
                                      vertical: 12,
                                    ),
                                    onPressed: _retryBootstrap,
                                    child: const Text(
                                      '다시 시도',
                                      style: TextStyle(
                                        fontFamily: 'Pretendard',
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          )
                        else
                          _TeamBody(
                            teamSetupId: _teamSetupId!,
                            currentUserId: uid,
                            eventTeam: _eventTeam,
                            onInviteSlotTap: () {
                              unawaited(_openPicker());
                            },
                          ),
                        const SizedBox(height: 32),
                        const _HelperText(),
                        const SizedBox(height: 32),
                        _InviteButtons(onKakao: _kakaoInvite),
                        const SizedBox(height: 100),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child:
                _bootstrapComplete &&
                    _teamSetupId != null &&
                    uid != null &&
                    uid.isNotEmpty
                ? _BottomSlotMachineCTA(teamSetupId: _teamSetupId!)
                : const _BottomCTA(isDisabled: true),
          ),
        ],
      ),
    );
  }
}

class _TeamProfilesData {
  final List<EventTeamMemberProfile> acceptedProfiles;
  final List<EventTeamMemberProfile> pendingProfiles;

  const _TeamProfilesData({
    required this.acceptedProfiles,
    required this.pendingProfiles,
  });
}

class _TeamBody extends StatelessWidget {
  final String teamSetupId;
  final String currentUserId;
  final EventTeamService eventTeam;
  final VoidCallback onInviteSlotTap;

  const _TeamBody({
    required this.teamSetupId,
    required this.currentUserId,
    required this.eventTeam,
    required this.onInviteSlotTap,
  });

  EventTeamSetupState _fallbackState() {
    return EventTeamSetupState(
      teamSetupId: teamSetupId,
      leaderUserId: currentUserId,
      acceptedUserIds: [currentUserId],
      pendingInviteeIds: const [],
    );
  }

  Future<_TeamProfilesData> _loadProfiles(EventTeamSetupState state) async {
    final acceptedProfiles = await eventTeam.buildMemberProfiles(
      state: state,
      currentUserId: currentUserId,
    );
    final pendingProfiles = await eventTeam.buildPendingInviteProfiles(
      state: state,
    );
    return _TeamProfilesData(
      acceptedProfiles: acceptedProfiles,
      pendingProfiles: pendingProfiles,
    );
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<EventTeamSetupState?>(
      stream: eventTeam.watchTeamSetup(teamSetupId),
      builder: (context, snap) {
        final state = snap.data ?? _fallbackState();
        if (snap.connectionState == ConnectionState.waiting &&
            snap.data == null) {
          return const Padding(
            padding: EdgeInsets.all(40),
            child: Center(child: CupertinoActivityIndicator()),
          );
        }
        if (snap.hasError) {
          return const Text(
            '팀 상태를 불러오지 못했어요.',
            style: TextStyle(color: _AppColors.textSub),
          );
        }
        final isLeader = state.leaderUserId == currentUserId;
        final canInviteMore = isLeader && state.remainingInviteSlots > 0;

        return FutureBuilder<_TeamProfilesData>(
          future: _loadProfiles(state),
          builder: (context, profSnap) {
            final acceptedProfiles = profSnap.data?.acceptedProfiles ?? [];
            final pendingProfiles = profSnap.data?.pendingProfiles ?? [];
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (var i = 0; i < 3; i++) ...[
                      if (i > 0) const SizedBox(width: 12),
                      Expanded(
                        child: i < acceptedProfiles.length
                            ? _MemberSlotCard(
                                profile: acceptedProfiles[i],
                                isMe:
                                    acceptedProfiles[i].userId == currentUserId,
                              )
                            : _EmptyInviteSlot(
                                onTap: canInviteMore ? onInviteSlotTap : null,
                              ),
                      ),
                    ],
                  ],
                ),
                if (pendingProfiles.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  _PendingInviteSection(profiles: pendingProfiles),
                ],
              ],
            );
          },
        );
      },
    );
  }
}

class _PendingInviteSection extends StatelessWidget {
  final List<EventTeamMemberProfile> profiles;

  const _PendingInviteSection({required this.profiles});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: _AppColors.primary.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(
                CupertinoIcons.time_solid,
                color: _AppColors.primary,
                size: 16,
              ),
              SizedBox(width: 8),
              Text(
                '\uc218\ub77d \ub300\uae30 \uc911',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  color: _AppColors.textMain,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final profile in profiles)
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '${profile.name} \u00b7 \ucd08\ub300 \ubcf4\ub0c4',
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: _AppColors.textMain,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            '\uce5c\uad6c\uac00 \ucd08\ub300\ub97c \uc218\ub77d\ud558\uba74 '
            '\ud300 \uba64\ubc84\ub85c \ucd94\uac00\ub3fc\uc694.',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class _MemberSlotCard extends StatelessWidget {
  final EventTeamMemberProfile profile;
  final bool isMe;

  const _MemberSlotCard({required this.profile, required this.isMe});

  @override
  Widget build(BuildContext context) {
    final url = profile.imageUrl;
    return Container(
      decoration: BoxDecoration(
        color: _AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white.withValues(alpha: 0.5)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.08),
            blurRadius: 40,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: AspectRatio(
        aspectRatio: 3 / 4,
        child: Stack(
          children: [
            Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    ClipOval(
                      child: url != null && url.isNotEmpty
                          ? Image.network(
                              url,
                              width: 64,
                              height: 64,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => _fallbackAvatar(),
                            )
                          : _fallbackAvatar(),
                    ),
                    const SizedBox(height: 10),
                    Text(
                      profile.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _AppColors.textMain,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      profile.mbti,
                      style: const TextStyle(
                        fontSize: 10,
                        color: _AppColors.gray400,
                      ),
                    ),
                    if (profile.isPending) ...[
                      const SizedBox(height: 6),
                      const Text(
                        '수락 대기 중',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: _AppColors.pendingSub,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
            if (isMe)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: _AppColors.primary,
                    borderRadius: BorderRadius.circular(10),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.1),
                        blurRadius: 2,
                      ),
                    ],
                  ),
                  child: const Text(
                    'ME',
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _fallbackAvatar() {
    return Container(
      width: 64,
      height: 64,
      decoration: BoxDecoration(
        color: _AppColors.gray200,
        shape: BoxShape.circle,
        border: Border.all(
          color: _AppColors.primary.withValues(alpha: 0.2),
          width: 2,
        ),
      ),
      child: const Icon(
        CupertinoIcons.person_fill,
        color: Colors.white,
        size: 36,
      ),
    );
  }
}

class _EmptyInviteSlot extends StatelessWidget {
  final VoidCallback? onTap;

  const _EmptyInviteSlot({this.onTap});

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: _AppColors.primary.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: _AppColors.primary.withValues(alpha: 0.3),
            width: 2,
          ),
        ),
        child: AspectRatio(
          aspectRatio: 3 / 4,
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 48,
                  height: 48,
                  margin: const EdgeInsets.only(bottom: 12),
                  decoration: const BoxDecoration(
                    color: _AppColors.surfaceLight,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black12,
                        blurRadius: 4,
                        offset: Offset(0, 2),
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.add_rounded,
                    color: _AppColors.primary,
                    size: 24,
                  ),
                ),
                Text(
                  onTap == null ? '대기' : '친구 초대',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                    color: onTap == null
                        ? _AppColors.gray400
                        : _AppColors.primary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomSlotMachineCTA extends StatelessWidget {
  final String teamSetupId;

  const _BottomSlotMachineCTA({required this.teamSetupId});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<EventTeamSetupState?>(
      stream: EventTeamService().watchTeamSetup(teamSetupId),
      builder: (context, snap) {
        final state = snap.data;
        final ready = state?.canStartSlotMachine ?? false;
        return _BottomCTA(isDisabled: !ready, teamSetupId: teamSetupId);
      },
    );
  }
}

class _Header extends StatelessWidget {
  final VoidCallback onBack;
  final String? teamSetupId;

  const _Header({required this.onBack, this.teamSetupId});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size(40, 40),
            onPressed: onBack,
            child: Container(
              width: 40,
              height: 40,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.05),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                CupertinoIcons.back,
                color: _AppColors.textMain,
                size: 24,
              ),
            ),
          ),
          const Text(
            '3명 팀으로 참여해요',
            style: TextStyle(
              fontFamily: 'Pretendard',
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: _AppColors.textMain,
            ),
          ),
          _HeartIconButton(teamSetupId: teamSetupId),
        ],
      ),
    );
  }
}

class _HeartIconButton extends StatelessWidget {
  final String? teamSetupId;

  const _HeartIconButton({this.teamSetupId});

  @override
  Widget build(BuildContext context) {
    if (teamSetupId == null) return const SizedBox(width: 40);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(40, 40),
      onPressed: () {
        HapticFeedback.selectionClick();
        Navigator.of(context).pushNamed(RouteNames.teamRequests);
      },
      child: SizedBox(
        width: 40,
        height: 40,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 40,
              height: 40,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.05),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                CupertinoIcons.heart,
                color: _AppColors.primary,
                size: 22,
              ),
            ),
            _PendingBadge(teamSetupId: teamSetupId!),
          ],
        ),
      ),
    );
  }
}

class _PendingBadge extends StatelessWidget {
  final String teamSetupId;

  const _PendingBadge({required this.teamSetupId});

  @override
  Widget build(BuildContext context) {
    final service = TeamMeetingRequestService();
    return StreamBuilder<int>(
      stream: service.watchPendingReceivedCount(teamSetupId),
      builder: (context, snap) {
        final count = snap.data ?? 0;
        if (count == 0) return const SizedBox.shrink();
        return Positioned(
          top: -2,
          right: -2,
          child: Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              color: _AppColors.primary,
              shape: BoxShape.circle,
              border: Border.all(color: _AppColors.backgroundLight, width: 2),
            ),
            alignment: Alignment.center,
            child: Text(
              count > 9 ? '9+' : '$count',
              style: const TextStyle(
                fontFamily: 'Pretendard',
                fontSize: 9,
                fontWeight: FontWeight.w800,
                color: CupertinoColors.white,
              ),
            ),
          ),
        );
      },
    );
  }
}

class _HeadlineGroup extends StatelessWidget {
  const _HeadlineGroup();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        Text(
          '팀 구성하기',
          style: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w700,
            color: _AppColors.textMain,
          ),
        ),
        SizedBox(height: 8),
        Text(
          '친구 2명을 초대해서 팀을 완성해보세요.',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: _AppColors.textSub,
          ),
        ),
      ],
    );
  }
}

class _HelperText extends StatelessWidget {
  const _HelperText();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: const [
          Icon(Icons.info_outline_rounded, color: _AppColors.gray400, size: 16),
          SizedBox(width: 8),
          Text(
            '3명이 모여야 매칭을 시작할 수 있어요',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: _AppColors.textSub,
            ),
          ),
        ],
      ),
    );
  }
}

class _InviteButtons extends StatelessWidget {
  final VoidCallback onKakao;

  const _InviteButtons({required this.onKakao});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onKakao,
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray200),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                  ),
                ],
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    CupertinoIcons.chat_bubble_fill,
                    color: _AppColors.kakaoYellow,
                    size: 20,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '카카오로 초대',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: () {
              HapticFeedback.lightImpact();
              SharePlus.instance.share(
                ShareParams(
                  text: '설레연에서 함께 3:3 미팅해요! 🎉',
                ),
              );
            },
            child: Container(
              height: 48,
              decoration: BoxDecoration(
                color: _AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: _AppColors.gray200),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.03),
                    blurRadius: 4,
                  ),
                ],
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    CupertinoIcons.square_arrow_up,
                    color: _AppColors.gray400,
                    size: 20,
                  ),
                  SizedBox(width: 8),
                  Text(
                    '공유하기',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      color: _AppColors.textMain,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _BottomCTA extends StatelessWidget {
  final bool isDisabled;
  final String? teamSetupId;

  const _BottomCTA({this.isDisabled = false, this.teamSetupId});

  void _onPressed(BuildContext context) {
    if (!isDisabled) {
      HapticFeedback.mediumImpact();
      Navigator.of(context).pushNamed(
        RouteNames.seasonMeetingRoulette,
        arguments: teamSetupId == null || teamSetupId!.isEmpty
            ? null
            : SeasonMeetingRouletteArgs(teamSetupId: teamSetupId!),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: isDisabled ? null : () => _onPressed(context),
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              _AppColors.backgroundLight.withValues(alpha: 0),
              _AppColors.backgroundLight,
            ],
            stops: const [0.0, 0.4],
          ),
        ),
        padding: EdgeInsets.fromLTRB(
          24,
          24,
          24,
          MediaQuery.of(context).padding.bottom + 24,
        ),
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            color: isDisabled ? _AppColors.gray200 : _AppColors.primary,
            borderRadius: BorderRadius.circular(28),
            boxShadow: isDisabled
                ? null
                : [
                    BoxShadow(
                      color: _AppColors.primary.withValues(alpha: 0.3),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    ),
                  ],
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                CupertinoIcons.game_controller_solid,
                color: isDisabled ? _AppColors.gray400 : Colors.white,
                size: 24,
              ),
              const SizedBox(width: 8),
              Text(
                '슬롯머신 돌리기 (1회 무료)',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: isDisabled ? _AppColors.gray400 : Colors.white,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
